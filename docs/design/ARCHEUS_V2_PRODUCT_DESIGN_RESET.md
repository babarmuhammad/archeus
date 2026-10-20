506 docs/design/ARCHEUS_V2_PRODUCT_DESIGN_RESET.md
# Archeus V2 — Product Design Reset (critique and proposal)

**Status: PROPOSED (2026-10-05) · design review only · awaiting the owner's review.** No
production code, prototype, P20 record or existing V2 document is changed by this file. No
decision in it is accepted. LV2-2 is not started.

**What this document is.** An independent critique of the V2 direction as it stands, and a
reset proposal for the product model, the information architecture, the mobile and desktop
shells, the visual language and the explanation model. It reads, and builds on, the other
session's uncommitted reassessment
([ARCHEUS_V2_PRODUCT_UX_REASSESSMENT.md](ARCHEUS_V2_PRODUCT_UX_REASSESSMENT.md), "LV2-X"), but
it does not adopt that document's recommendation by default. Where this review agrees, it says
so in one line and moves on; where it disagrees or goes further, it says why.

**Sources read.**
- The V2 objective: [ARCHEUS_V2_UI_ARCHITECTURE.md](ARCHEUS_V2_UI_ARCHITECTURE.md) (top matter,
  §A–§M).
- The LV2-1 gate and its evidence: [ARCHEUS_V2_LATER_UI_LV2_1_GATE.md](ARCHEUS_V2_LATER_UI_LV2_1_GATE.md),
  `prototypes/v2-later/results/lv21/` (`b_desk_now.png`, `b_phone_now.png`, `human.json`).
- The LV2-2 plan: [ARCHEUS_V2_LATER_UI_LV2_2_PLAN.md](ARCHEUS_V2_LATER_UI_LV2_2_PLAN.md).
- LV2-X and its captures: `prototypes/v2-later/results/lvx/` (A, B, C × home, live, decide).
- The P20 gate's reconciliation:
  [../architecture/p20-design-gate.md](../architecture/p20-design-gate.md) §14.

**Evidence classes, kept apart.**
- *Automated:* the LV2-0/LV2-1/LV2-X probes. They are floors, not judgements.
- *Design review:* this document. It is judgement and is marked as such.
- *Human:* exactly one informational observation (P1, below). It is not statistically valid,
  does not represent users, and decides nothing here.

---

## 1. Executive diagnosis

**The product was optimised away from its own objective.** V2's architecture states the goal
plainly: *more presence, identity, depth, clarity and visible intelligence, while staying calm
enough to use every day*. The LV2 lab then measured only what it could count: screens per
answer, row height, bundle bytes, machine strings, contrast, overflow. Every one of those
metrics rewards removing structure. None measures orientation, explanation, identity or trust.

<!-- RECOVERY GAP: lines 41-140 of the original 506-line file could not be located in any
     transcript. Based on the heading index (recovered separately via `grep -n "^#"`) this spans
     the rest of "## 1. Executive diagnosis", all of "## 2. Product mental model", and all of
     "## 3. What Archeus should communicate on launch" (original headings at lines 33, 87, 116;
     "## 4. Mobile application model" at line 141 is where the recovered text below resumes). -->

## 4. Mobile application model

Designed as its own application, not the desktop narrowed.

**4.1 The shell.**

| Element | Specification |
|---|---|
| **App bar** (top, every screen) | Left: the presence mark (its state tint and, when work is live, its quiet motion, §7.8) + the **place title** ("Home", "Decisions", "Missions", "Activity"); a large title on each place's root that collapses on scroll. Right: **Tell** (+) and **Stop** (compact, LD-7 placement). On a pushed page the left becomes **Back + the parent's name** |
| **Tab bar** (bottom, docked, safe-area padded, not floating) | **Home · Decisions · Missions · Activity**, icon over label, a numeric badge on Decisions only. Control is not a tab (rare, and it holds the risky settings); it is reached from Home's status card and from a menu on the app bar |
| **Live mini-bar** | When work is live, a slim bar **docked above the tab bar, inside the bar's container** (it never overlays content, unlike LV2-1's floating strip): "2 running · Fix the flaky date test · step 4 of 7". Tap opens that mission; a second running mission is "+1". Absent when nothing runs |
| **Stop band** | When stopped, the app bar becomes the stop band on **every** screen (LV2-X SS-5): when, from where, what is held, *Resume work…* |

**4.2 Places and their roots.**

| Place | Root content | Pushes to |
|---|---|---|
| **Home** | Status card (presence + safety + one statement), *Your next* (the first decision, full), live work (up to 3), problems, since you looked (strip + last 3) | decision page, mission page, Activity filtered |
| **Decisions** | Grouped: *Expiring soon*, *Plans to approve*, *Results to review*; each card shows why it asks and the deadline | decision page |
| **Missions** | Segmented: *Active* · *Blocked/failed* · *Done*; a project filter chip at the top; each row shows its lifecycle line | mission page |
| **Activity** | The record: since you looked, then earlier (day-scoped needs DR-7; until then "since you looked" and paging back, which Core supports today) | the mission or decision it names |

**4.3 Action hierarchy.** One primary action per screen, at the bottom third (one-handed):
on a decision page, the decision bar; on a blocked mission, its recorded next action; on Home
when idle, *Tell Archeus*. Destructive and rare actions (Stop, Reject, Cancel) are deliberate:
Stop at the top, Reject never the default, never adjacent-and-equal to Approve without its
consequence shown.

**4.4 Mission detail (pushed page).** Header: state chip (word + colour), title, **project
chip** (§7.5), branch in caption. Then B's **vertical spine** (LV2-X's best phone screen):
the six phases, done ones collapsed to one line, the current one expanded with its steps and
the explanation frame (§8). A sticky bottom bar appears only when the mission needs the user.

**4.5 Approval / review flow.**
1. Entry: Home's *Your next* card, the Decisions tab, the live mini-bar, or a notification
   (P21 owns notifications).
2. **Decision page** (LD-5: a full page): *What you approve* (the plan's tasks), *What happens
   if you approve / ask for changes / reject* (each from the state machine), *Why Archeus asks*
   (the rule in words; rule strings collapsed), *What changed since the last version*, *Your
   request*, *What Archeus does not know* (named gaps).
3. **Sticky decision bar** (bottom): the Approve consequence in one line above three ≥ 48 px
   buttons; the deadline in the bar.
4. **After deciding:** the page states Core's recorded result ("Approved at 15:14. Archeus
   started *Build the site*.") only when Core confirms it, then offers **Next decision** if one
   waits, else back to where the user came from. No undo is offered: Core has none.
5. Back from the decision page decides nothing and returns to its origin.

**4.6 E-stop visibility.** Stop in the app bar on every screen, quiet at rest (outlined, stop
ink), unmistakable when primed (LD-7, wording per LV2-X SS-4). The stopped state changes the
whole frame (stop band). The mechanics are P20's and LD-7's (§11).

**4.7 Back behaviour.** Each tab keeps its own stack; re-tapping the active tab pops to its
root; system back pops one level and **never leaves the app from a pushed page**; from a
tab's root, back goes to Home, and only from Home's root does it leave. A notification opens
the decision page with Decisions' root beneath it, so back has somewhere honest to go.

**4.8 Empty, loading, error.**

| State | Behaviour |
|---|---|
| **Loading** | The last snapshot is shown at once (V1 already has the offline snapshot), marked "as of 15:12, updating…"; skeletons only where nothing was ever read |
| **Empty (first run)** | Home explains the product in three lines and the six-phase line with one sentence per phase, plus a large *Tell Archeus* field with two example missions |
| **Empty (quiet day)** | "Nothing needs you, and nothing is running." + what finished today + *Tell Archeus* |
| **Core unreachable** | The frame says "Core cannot be reached · state not known"; the screen shows the snapshot greyed with its time; actions that need Core are disabled **with the reason**; the safety copy points to the tray and `archeus estop` (P20 slice B's rule: the page holds no local stop authority) |
| **Error on an action** | Inline, next to the action, in Core's words; never a toast |

---

## 5. Desktop application model

A **control surface**: simultaneous visibility of what needs me, what runs and what happened,
with context persistent instead of one level down.

**5.1 Regions (1,440 × 900 reference).**

| Region | Width | Content |
|---|---|---|
| **Frame** (top bar, 48–56 px) | full | presence mark + "Archeus" + presence in words ("Working on 2 missions · 2 agents") · safety in words · Core connection · *Tell Archeus* field (Ctrl K) · Stop |
| **Rail** (left) | 220–240 px | places (Home, Decisions + badge, Missions, Activity, Control) and **Projects** with their identity marks and active counts; selecting a project **scopes every place** (a filter, not a place) |
| **Main** (centre) | fluid | the place's content: on Home, the briefing (§9.1) |
| **Context pane** (right) | 360–420 px, collapsible | whatever is selected: a decision's summary with its consequence, a mission's spine and frame. On Home with nothing selected, it shows **Archeus's activity**: agents working, on which account, what they run, recent checks |

**5.2 How desktop answers the five questions.**

| Question | Where | How |
|---|---|---|
| What is happening | frame presence + Home's live-work band + the context pane's agents | each running mission as a tile with its lifecycle line, step, elapsed, next; agents as a compact list |
| What needs me | Home's statement + *Your next* card + the decision list; the rail badge | first decision fully explained; the rest ranked by deadline |
| What can I inspect | any row → the context pane; double-click or Enter → the full page | inspection without losing the overview |
| What happened | Home's since-you-looked strip; Activity | counts by outcome + the last 5 events, each linking to its object |
| What is safe/dangerous | frame safety word; Stop; problem rows in the blocked tone; consequences on every decision button | danger is a colour **and** a word **and** a position, never one alone |

**5.3 One representation per set.** Home shows each mission once. The lifecycle line is drawn
**on the mission** (its row, tile or page), not as a second, column-based copy of the list. B's
pipeline is kept as an **optional Missions view** ("by phase"), where it is the whole content
and its scale can be designed for, not as Home's centre.

---

## 6. Information architecture proposal

**6.1 The candidates, evaluated** (design review).

| Candidate place | Keep as a place? | Reason |
|---|---|---|
| **Now / Home** | **Yes** | the briefing; the only place that combines all five layers |
| **Work / Missions** | **Yes** | the central object; all work, filterable, with lifecycle views |
| **Decisions / Attention** | **Yes** | the user's only mandatory work; a phone needs it one tap from anywhere, with a badge |
| **History / Activity** | **Yes** | how trust is built, and how a returning user re-orients; currently the most hidden |
| **Projects / Context** | **No — a scope, not a place** | users do not delegate to a repository; a project is a filter and an identity on every object (rail on desktop, chip filter on phone). World (the graph) stays a secondary view inside Missions or Control |
| **System / Safety** | **No — the frame, plus Control** | safety is a state on every screen, never a destination; Control holds the rare settings (autonomy, accounts, clients, policy) |

**6.2 Proposed model.** *Four places, one frame, one scope:*
- **Frame:** presence, safety, connection, Tell, Stop.
- **Places:** Home · Decisions · Missions · Activity (+ Control, secondary).
- **Scope:** All projects ▾ / one project.

**6.3 Relation to LD-2 and LV2-X.** LD-2's three places (Now / Needs you / Missions) lack
Activity and treat the project as a caption. LV2-X's directions add Record (A, C) or make
missions primary (B). This proposal is closest to **A's places with B's mission line and C's
evidence**, plus two things none of them has: **presence** (Archeus's own activity) and the
**project scope with identity**. It is a proposal; LD-2 stays APPROVED until the owner changes
it.

**6.4 Naming** (open; D-2 keeps V1's names until the owner decides). Proposed: *Home,
Decisions, Missions, Activity, Control*. "Needs you" is warm but is a state, not a place;
"Attention" is a V1 term the user never says.

---

## 7. Visual language proposal

Keep the minimalist philosophy: calm, dark-first, tonal depth, no glass or blur, motion only
when something real happens. **Add structure, not decoration.**

| # | Area | Proposal |
|---|---|---|
| 7.1 | **Hierarchy** | Three registers on every screen (LV2-X VH-1 agrees): *statement* (one per screen), *object* (titles), *fact* (captions, mono for times and counts). Plus a fourth the lab lacked: **zone labels** in small caps with counts, clearly darker than content but heavier than LV2-1's 17 px regular |
| 7.2 | **Typography** | §F stays (Segoe UI Variable; Display for the statement). Desktop: statement 30/36, title 16/22 semibold, body 13/20, caption 12/16, label 11/14 small caps +6 % tracking. Phone: statement 28/34, title 17/22, body 15/22, caption 13/18. Tabular figures everywhere a number changes |
| 7.3 | **Spacing** | 4-pt grid. Between zones 32 px (desktop) / 24 px (phone); inside a card 16 px; between rows 12 px. Zones are separated by **space and a label**, not only by hairlines |
| 7.4 | **Surfaces** | By role (LV2-X VH-4 agrees): **cards** for things you act on (decisions, *Your next*), **tiles** for live things (running missions), **rows** for things you open, **lines** for things you read (activity). One tonal step per role; selection is a 2 px focus ring, not a fill |
| 7.5 | **Project identity** | Each project gets a **monogram mark** (two letters in a small rounded square, with a per-project **shape or pattern** from a fixed set of six, *not a hue*, so colour stays reserved for state). It appears on every row, tile, card and in the rail. This directly answers "which project" without spending colour |
| 7.6 | **Status indicators** | State is a **chip**: word + colour + shape (LV2-X VH-3). The lifecycle line (B) on every mission object: six nodes, past solid, current lit in its state colour, future faint. Progress inside Run as step N of M, never a fake percentage |
| 7.7 | **Semantic colour** | Unchanged and strict: amber = waits for you; red = blocked, failed, stopped; blue = running; green = done/passed; violet = planning; **nothing else is coloured**. Danger is never colour alone |
| 7.8 | **Motion** | Purposeful only, compositor-only (transform, opacity), **zero frames at idle** (V2 rule). Three uses: (a) **presence** — the mark breathes slowly only while executions are live, still otherwise; (b) **arrival** — a changed row highlights once (V1's row pulse); (c) **progress** — the lit node moves along the line when Core records a phase change. Reduced motion: all three become static state changes |
| 7.9 | **Iconography** | A small, consistent set that carries meaning: six phase glyphs, object glyphs (mission, decision, check, agent, project), check results (passed/failed/not run). Navigation icons over labels on the phone. No decorative icons |
| 7.10 | **Density** | Two densities on desktop (comfortable default; compact for heavy users), one on the phone. Density changes spacing, never removes a fact class |
| 7.11 | **Empty states** | Designed: one sentence of state, one of what Archeus does, one action. Never blank, never an illustration |
| 7.12 | **Progressive disclosure** | Row → card/pane → page; each depth **adds** slots of the explanation frame (§8), never repeats the previous depth (LV2-X VH-11 agrees). Rule strings, IDs, hashes and raw output live only at page depth, collapsed |

**On LE8 (D-5).** LE8 applied good platform principles (inset separators, list headers) to a
structure that was already too thin. Its automated pass is a floor, not a reason to keep its
shape. Keep: §F, the one-row decision bar, the inset separators. Re-derive: everything that
governs hierarchy and grouping.

---

## 8. Explainability model

Archeus is agentic, so the interface must make its behaviour **predictable** (what will it do),
**legible** (what is it doing) and **accountable** (what did it do, and how do I know).

**8.1 The explanation frame** (LV2-X §7.1, adopted with one addition):

| Slot | The user's question | Source (recorded or derived; never interpreted) |
|---|---|---|
| **What it decided** | What did Archeus choose? | the plan and its version; the route decision (which agent, which account, why: `RouteDecision`); policy decisions in words |
| **Why** | Why this, why ask me? | matched policy rules in words; the recorded *because* (two hops at most) |
| **Doing now** | What is it doing right now? | the phase, step N of M, the task title, elapsed. The *current operation* inside a step is **not recorded** (DR-6, P21's) and is named as such |
| **Waiting for** | What is it waiting for? | an approval (whose, by when), a review, a blocked check, a resource (an account at its limit), or nothing |
| **Verified** | What did it check? | `Verification.checks` by name with result; "not verified yet" when none ran |
| **What changed** | What did it change? | the branch and commits it recorded; files changed **only if Core records them** (otherwise "not recorded"; LV2-X's honesty rule forbids "changes 14 files" without a contract) |
| **If you approve** | What happens next? | each action's consequence from `states.py` + the plan's tasks; the expiry and what expiry does |
| **Not known** | What can't Archeus tell me? | the named gaps (environment DR-4, remote DR-2, current operation DR-6), once per block |

**8.2 New: the mission's decision journal.** On the mission page, a short chronological list
of **Archeus's own decisions** on that mission: plan v1 written, route chosen (agent, account,
reason), policy asked you, you approved, check failed, re-planned. Each is a recorded event. It
is how a supervisor learns to trust (or correct) the system's judgement over time.

**8.3 Rules** (LV2-X §7.2, adopted): consequences come from the state machine; provenance is
structural (`data-src`), not narrated; two hops, no interpretation; deadlines carry their
consequence; say what is not known once.

---

## 9. Above-the-fold specifications

### 9.1 Desktop, 1,440 × 900, Home, busy

| Area | Content (top to bottom) |
|---|---|
| **Frame** (56 px) | ◭ Archeus · **Working on 2 missions · 2 agents** · ● Accepting new work · Core connected — [Tell Archeus what to do… Ctrl K] — [■ Stop all work] |
| **Rail** | Home · Decisions ③ · Missions · Activity · Control — PROJECTS: [AR] archeus 3 · [WS] website 1 · [IN] invoicing 4 |
| **Main: statement** | "**3 decisions wait for you.** The first expires in 8 min." + one caption line: "2 running · 1 blocked · 1 failed · 2 done since you looked at 14:30" |
| **Main: *Your next*** (card) | [WS] *Deploy release notes to staging* · PLAN APPROVAL v2 · expires 15:20 · Why: "your policy asks before every deploy" · If you approve: "Archeus starts *Build the site*, then 2 more tasks" · [Review] |
| **Main: zones** (two columns) | Left: WAITING FOR YOU 2 (rows) · PROBLEMS 2 (rows with *because* and *next*). Right: RUNNING NOW 2 (tiles with lifecycle line, step, elapsed, *then*) |
| **Main: since you looked** (strip) | 2 done · 10 checks passed · 1 failed · 3 decided — and the last 3 events, each linking |
| **Context pane** | Nothing selected: **ARCHEUS NOW** — 2 agents working (Claude Code on *work* account: *Fix the flaky date test*, step 4 of 7; … verifying *Rename the billing module*), the next scheduled automation if one exists (`Automation`) |

Not above the fold: Done today's full list, the record beyond 3 events, any rule string, any ID
or hash, usage and cost.

### 9.2 Desktop, Home, idle

Statement: "**Nothing needs you, and nothing is running.**" Then: what finished since you
looked (strip), *Tell Archeus* as the primary action (large field, two example missions), and a
one-line "how a mission moves" with the six phases. Context pane: "Archeus is idle." and the accounts
Core reports as usable.

### 9.3 Phone, 390 × 844, Home, busy (top to bottom)

| Px (approx.) | Content |
|---|---|
| 0–56 | App bar: ◭ (breathing) **Home** · (+) · [■ Stop] |
| 56–176 | **Status card:** "3 decisions wait for you." · ● Accepting new work · "2 running · 2 problems" |
| 176–400 | ***Your next*** card: [WS] Deploy release notes to staging · lifecycle line with Approve lit · "Your policy asks before every deploy" · "expires 15:20 (in 8 min)" · chevron |
| 400–560 | RUNNING NOW 2: two compact tiles (project mark, title, step N of M, line) |
| 560–700 | PROBLEMS 2: two rows with *because* |
| 700–760 | Live mini-bar (docked): "2 running · Fix the flaky date test · step 4 of 7" |
| 760–844 | Tab bar: Home · Decisions ③ · Missions · Activity |

Since-you-looked and the remaining decisions are one scroll below.

### 9.4 Phone, stopped

The app bar is the stop band: "**All work stopped** at 15:14 from this computer. New work is
refused." Status card: what was stopped, what is held, **Resume work…** (its authentication
requirement is P20's D10, unresolved for the local device: §11). Tabs unchanged.

---

## 10. What to remove / what to add

**Remove (or move down a level).**
- Counts without nouns ("3 need you · 2 running · 2 stopped").
- "Stopped" for anything but the emergency stop (blocked and failed are their own words).
- Approve/Reject on list rows (decide on the decision page only).
- Two representations of the same missions on one screen.
- Mono branch names, IDs and hashes at row level (branch moves to caption; IDs to the page).
- Rule strings above page depth.
- Floating overlays over content (LV2-1's phone strip).
- Footnote-sized outcomes and collapsed "since you looked".

**Add.**
- Presence: what Archeus itself is doing, in the frame and the context pane.
- *Your next*: the first decision, fully explained, promoted above everything.
- Project identity marks, and a project scope.
- Activity as a place; since-you-looked as a strip on Home.
- Zone labels with counts; three typographic registers.
- The lifecycle line on every mission object.
- The decision journal on the mission page.
- Designed empty, loading and unreachable states.

**Never show (anti-noise rules).** Charts on Home; usage and cost on Home (Control); live log
streams on Home; progress percentages Core does not record; more than five events on Home;
decorative animation; any fact without a source; the word "armed" (LV2-X SS-1); an orb, ring
or "AI core" visual (V2 architecture's anti-JARVIS rule).

---

## 11. P20 constraints

**Constrained by P20 semantics (not redesignable without a P20/Core gate).**

| Area | P20 fact | Design consequence |
|---|---|---|
| Emergency stop with Core down | Only the tray and `archeus estop` hold that authority; the page holds none (slice A, slice B §12 item 15) | The page may say "nothing is confirmed stopped" and point to the tray/CLI; it may never claim a stop it cannot perform |
| No new work until re-armed | Core refuses new work while stopped | The stop band's "new work is refused" is a fact the UI must keep |
| Re-arm counts only on Core's confirmation | slice B §12 item 18 | *Resume work…* shows nothing as resumed until Core answers |
| Accidental activation | item 83's requirement; today a confirmation dialog (slice B); LD-7's two-press replaces it after P26 | any e-stop interaction must keep this requirement tested (P20 §14.F V2-2) |
| Re-arm authentication | **D10 as approved: PIN step-up when re-arming from a paired (non-local) device.** LV2-X SS-4/SS-6 say resuming needs a PIN on every surface | **Unresolved (P20 §14.F V2-3). This document chooses neither.** The phone copy above is correct for a paired phone under either reading; the desktop copy must wait for the owner |
| The word "armed" | P20's approved copy uses "Armed" for running normally; Core uses it for stopped | V2 copy avoids the word; whether V1 changes is the owner's (P20 §14.F V2-1) |
| Notifications | D8 moved them to P21 | the notification entry in §4.5 is P21's, not P20's |
| Authentication, stream cap, shell credential | slice C's record (P20 §12 item 34) | invisible to design; never relaxed by a design need |
| Check output at rest | DR-8 hands its at-rest question to P20's secrets review (open) | the UI shows check names and results only until DR-8 and D7 decide |

**Freely redesignable.** Layout, information architecture, place names (subject to D-2's
record), the shells, the visual language, motion within V2's rules, explanation copy, the
presentation of every P20 state (as long as its meaning is kept), density, iconography.

---

## 12. Decisions that remain valid

| Decision | Why it stays |
|---|---|
| **LD-3** (scope: Now rebuild, approval screen, plain labels, visible verification) | exactly the four outcomes this reset needs |
| **LD-5** (phone decision is a full page) | the explanation frame needs it |
| **LD-7's semantics** (two presses, 3 s lapse, re-arm through P20's step-up) | a safety interaction; only its wording changes (LV2-X SS-4) |
| **LD-8** (no warm grey), **LD-9** (every clause traceable) | principles this reset depends on |
| **D-1 as a data rule** (no remote, operation or environment until their contracts) | honesty |
| **D-3, D-4, D-6**; **§F typography**; **LD-1 as a cap** | unaffected |
| The honesty rules and the LE-2 corrections | non-negotiable |
| The DR gates as drafts | contracts are decided there, not here |
| All P20-owned semantics | §11 |

## 13. Decisions that should be reopened

Each was approved **on automated evidence only**; none was validated by people (W2 skipped by
the owner's decision, not reopened here).

| Decision | Why reopen | Proposed treatment |
|---|---|---|
| **LD-2** three places | a navigation model without Activity, presence or project scope | replace by §6's model, if the owner agrees |
| **D-2** V1 names | follows the model | rename with the model (§6.4) |
| **D-5** LE8 as the presentation target | a polish of a too-thin structure | keep §F and the one-row bar; re-derive hierarchy |
| **The LV2-1 density targets as goals** | they rewarded removal | keep as floors only (no clipping, contrast), never as targets |
| **The LV2-2 plan** | assumes LD-2 and D-5 | on hold (already); re-plan after the model is chosen |
| **LV2-X's recommendation (B as base)** | proposed, not decided; B duplicates the mission set on desktop and has no presence | keep B's **mission line** and phone spine; take A's frame and zones, C's evidence; add presence and project scope (this document) |
| **PR-5** (treatment C state figures) | its human identification gate is still open | stays as recorded; re-examine once state is a chip with a word |

## 14. Proposed design principles

1. **Clear before clean.** A screen is done when it answers the supervisor's five questions,
   not when nothing more can be removed.
2. **Archeus is visible.** The system's own activity has a place on every screen.
3. **One statement per screen.** Then labelled zones; never a tally.
4. **The first thing to do is promoted.** One decision, fully explained, above the rest.
5. **Every count has a noun; every state has a word.**
6. **One representation per set per screen.**
7. **Project is identity and scope, not a caption.**
8. **Explain in the frame:** decided · why · doing · waiting · verified · changed · next ·
   not known.
9. **Consequences before buttons.**
10. **Colour is state; identity is shape.**
11. **Motion only when something real happens; stillness at idle.**
12. **Phone is an application:** titles, tabs, stacks, a docked live bar, honest back.
13. **Desktop is a control surface:** overview and detail together.
14. **Quiet is designed;** unknown is said once.
15. **Safety semantics are P20's;** design changes their words and placement, never their
    meaning.

## 15. Proposed next design phase

**LV2-R (reset), design only, no production code, no human study unless the owner asks.**

| Step | Content | Exit |
|---|---|---|
| R0 | The owner reviews this document and LV2-X together; chooses the model (§6) and answers §16's questions | recorded decision |
| R1 | **One** composite prototype (not three) on the LV2-0 fixture: desktop and phone shells, Home busy/idle/stopped/unreachable, Decisions, a decision page, a mission page, Activity, presence, project scope | captures of every state |
| R2 | Stress: 25 open missions, 5 projects, look-alike titles, a real V1 Core data replay (every fact known or derived) | no invented fact; zones hold at scale |
| R3 | Structured owner review against the five supervisor questions and the 5–10 s table (§2), on both devices; LV2-X's twelve questions kept as a second lens | the owner's sign-off, or named changes |
| R4 | Qt = Chromium on every layout fact; reduced motion, forced colours, 200 % text, light theme | automated floors green |
| R5 | Re-plan LV2-2 on the chosen design | the owner's authorisation |

## 16. Explicit non-goals

- No production UI, no change to V1, P20, Core or any API.
- No new data contract; every gap is named with its existing DR (or "not recorded").
- No human study, no recruitment, no revival of W2. P1 stays one informational observation.
- No change to any recorded decision: everything here is a proposal.
- No JARVIS-style orb, no dashboard of charts, no decorative motion.
- No resolution of P20's open items (V2-1 to V2-5, D10's scope, O1–O3, D6, D11–D14, ADR-0021).
- LV2-2 is not started.

### Questions for the owner

| # | Question |
|---|---|
| R-Q1 | Is the model "four places, one frame, one scope" (§6.2) the right reset, or should a single primary object (missions, as in B) lead? |
| R-Q2 | Should presence (Archeus's own activity: agents, accounts) be first-class on Home and in the frame? |
| R-Q3 | Project identity by monogram + shape (colour stays state-only): acceptable? |
| R-Q4 | Activity as a place now (since-you-looked supported today; a calendar day needs DR-7)? |
| R-Q5 | One composite prototype (R1) instead of three directions? |
| R-Q6 | D10's scope versus "resuming needs a PIN" (P20 V2-3): the owner's call before any resume copy is final |
