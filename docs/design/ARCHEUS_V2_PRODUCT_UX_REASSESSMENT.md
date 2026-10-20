# Archeus V2 — Product UX / Information Architecture Reassessment (LV2-X)

**Status: PROPOSED (2026-10-05) · design and evidence only · awaiting the owner's review.**
No production file changes. Nothing is committed. No existing phase, gate, decision or evidence
record is closed, renumbered or rewritten by this document: LV2-0, LV2-1, the LV2-2 plan and the
DR gates stay exactly as recorded. LV2-2 is **not authorised** and is on hold behind this phase.

**Update 2026-10-06: the owner accepted Direction E; LV2-X.1 is closed. Every owner decision for the V2 UI is in §19.**

Prototype: `prototypes/v2-later/lvx/` (three directions × seven states × desktop and phone).
Captures and checks: `prototypes/v2-later/results/lvx/`. Run it: §A.

---

## 0. The answer first

**Why the current V2 feels too minimal.** The lab's measurements reward removing structure, and
none of them measures orientation, explanation, identity or trust (§2.2). Over two phases the
prototype converged on the least structure that still passes its probes. The result is
*technically valid*: zero clipping, contrast floors held, fewer screens per answer. It is not yet
*good product design*. The first screen is a tally of nouns it never defines ("3 need you ·
2 running · 2 stopped"). Every row is the same run-on sentence. The desktop is a phone column with
the right third of the window empty. The safety state is not shown at all, while the stop button is the
loudest object on the page.

**What Archeus is, as a model.** *You delegate missions; Archeus plans and does the work with
your coding agents, stops at the decisions your policy reserves for you, proves what it did, and
can be stopped at any moment.* Four concepts follow, in screen priority (§3):

1. **The safety and system state** — the frame, always present.
2. **Decisions** — the user's part of the work.
3. **Missions in motion** — the work itself.
4. **The record and its verification** — the proof.

Projects and repositories are context on every mission, not a primary place.

**What changes.** Every screen gets one statement, then structured zones. State is always a word.
Every important state is explained in a fixed frame: *what · where · why · evidence · next*,
plus *what Archeus does not know* on a decision. The consequence of every decision button is
derived from Core's state machine, so it costs no new data. "Stopped" is reserved for the
emergency stop. The word "armed" leaves V2's surfaces: Core already uses it in both opposite
senses (§8.1).

**Three directions were built (§9),** each a different product rather than a different theme:

- **A, Supervision desk.** A zoned control surface.
- **B, Mission lines.** The mission is the object, drawn on its lifecycle line.
- **C, Brief & record.** Archeus explains itself in sentences built from facts, beside a
  checkable record.

Each direction has seven states on desktop and phone. They are compared against the owner's twelve
questions in §10.

**Recommendation (§11): B as the base.** It borrows A's safety frame and Today strip, and C's
evidence presentation and Record place. The matrix scores the three within a point of each other.
B wins because its weaknesses can be fixed by adding parts, while A's lack of identity and C's
slow scanning are built into their structure.

---

## 1. What this phase is

| | |
|---|---|
| **Question** | What should Archeus look like, and how should it explain itself, before the V2 information architecture is locked into production? |
| **Not** | Another optimisation of the LV2-1 lab, a human-test programme, a production change, a data-contract implementation, a V1 redesign |
| **Method** | First principles from Core's actual responsibilities (§3); diagnosis of the current prototype from its own captures (§2); three materially different directions prototyped on the LV2-0 fixture with the same honesty rules (§9); structured comparison against the owner's twelve questions, using automated checks only where they can answer (§10) |
| **Evidence kept apart** | *Automated:* the capture check (§A.2). *Design review:* this document's own evaluation, clearly marked as judgement. *Human:* **none**. W2 was intentionally skipped by owner decision; the one P1 trial is informational only and is not used here as evidence for anything |

### 1.1 What stays exactly as recorded

- **LV2-0 and LV2-1.** Every result, mutation-verified gate and capture.
- **The LV2-1 decisions of 2026-10-05.** LD-2, LD-3, LD-5, LD-7, LD-9, D-1, D-2 and D-5 stay
  APPROVED in the gate (§1.1), recorded as approved on the automated evidence and without human
  validation. §14 says which of them this reassessment proposes to treat as candidates. That
  classification is a **proposal to the owner**, not a change to the record.
- **DR-1, DR-2, DR-3, DR-4 and DR-8.** These stay draft gates. DR-8 stays linked to P20's
  secrets review. Nothing here implements a data contract. Where a direction would need one, the
  screen says so (§12).
- **The honesty rules.** No fact is invented. Every rendered fact is known, derived by a stated
  rule, or named as not recorded with its gate. The LE-2 corrections are preserved: no remote, no
  environment, no "Into main", no "deploys to staging", and no third because-hop.

---

## 2. Diagnosis: why the current V2 direction feels too minimal

### 2.1 What the current prototype shows

From the LV2-1 default-arm captures `results/lv21/shots_af/b_desk_now.png` (1,440 × 900) and
`b_phone_now.png` (390 × 844). These are design observations, not test results.

| # | Observation | Where | Why it matters |
|---|---|---|---|
| X-1 | **Nothing says what Archeus is.** The only identity is a 13 px "Archeus · Core connected". The first content is "3 need you · 2 running · 2 stopped": three counts of a noun the screen never names | desktop, phone | A first-time viewer cannot say what the product does, so the five-second question fails before any row is read |
| X-2 | **The headline is a tally, not a state.** It does not say whether anything is urgent, whether it is safe to leave, or what is due first | desktop, phone | "Can I leave it alone?" is the supervisor's main question, and it has no answer on screen |
| X-3 | **"Stopped" means two things.** "2 stopped" counts one *blocked* and one *failed* mission, while "Stop all" is the emergency stop | desktop, phone | The most safety-critical word is overloaded on the same screen |
| X-4 | **The safety state is invisible, but its control is the loudest thing on screen.** Nothing shows whether Archeus is accepting work. The red-outlined "Stop all" is the strongest element on desktop and the largest control in the phone header | desktop, phone | The priority is inverted: the state is silent and the emergency control shouts. That makes the product feel like an emergency console while still not saying whether it is safe |
| X-5 | **One typographic register.** Every row is a bold title plus regular clauses joined by "·", then a mono line, with four to six facts at equal weight. State is a 16 px glyph with no word | desktop, phone | Hierarchy is flattened into prose, so scanning means reading |
| X-6 | **Approve from the list.** Approve and Reject sit on the Now row next to a plan whose content, reason and consequence are not on screen | desktop | Compact, but it asks for trust it has not earned. The owner's §9 requires the approval UI to *feel trustworthy*, not merely compact |
| X-7 | **The desktop is the phone column.** Content is 756 px wide on a 1,440 px window: the right 452 px (31 %) are empty, and there is no persistent context, selection or detail | desktop | The desktop is a larger phone, not a control surface |
| X-8 | **Recent activity is hidden.** "Since you looked · 14 changes" is collapsed. "Today: 2 verified · 1 failed · 1 blocked" is a footnote | desktop, phone | What happened while I was away is the second question a returning user asks, and it is the least visible thing on screen |
| X-9 | **Verification is a phrase, not an object.** "3 of 3 checks passed" never shows which checks | desktop, phone | Trust needs evidence that can be seen, not only counted |
| X-10 | **No "next".** Rows say what *is*, never what Archeus will do next or what it is waiting for | desktop, phone | Without "next", the user cannot predict the system, and prediction is most of trust |
| X-11 | **The phone is not an application.** There is no title and an unexplained "+". The headline wraps to three lines and takes a quarter of the first screen. The floating running strip and the capsule tab bar sit over the content. Text runs full-bleed on the background with no grouping surface | phone | It reads as a carefully arranged web page on a phone, in the owner's words |
| X-12 | **Section labels barely differ from content.** "Needs you" and "Running" are 17 px regular in secondary ink | phone | Structure that cannot be seen does not orient |

### 2.2 The root cause: what the measurements could and could not see

The LV2-0/LV2-1 probes were sound for what they measured, and each was mutation-verified. Every
one of them rewards *removing* something:

| Measured (and passed) | Rewards | Cannot see |
|---|---|---|
| Screens to answer a question (LD-2: phone 5.2 → 1.5) | fewer, denser screens | whether the answer is *understood* |
| Row height, wraps, characters (density probe) | shorter rows | whether a row's facts have a hierarchy |
| Bundle KB (LD-1) | less markup | value per byte |
| Machine strings and ISO times at depth 1–2 → 0 (LD-9) | plainer words | whether the words *explain* |
| Contrast, clipping, overflow, 200 % text | less on screen | identity, orientation, trust |
| One-row bar −56 px, 20 px headers −40 px (D-5) | less vertical space | whether the decision feels safe to take |

No probe measured the owner's actual questions: *what is this, what is happening, why, what
next, can I trust it, can I leave it.* So the optimisation could only move toward less. LE8's
design pass then applied HIG *principles* (inset separators, list-header sections) to a structure
that was already minimal. It polished the surface but could not add the missing hierarchy.

**Technically valid is necessary and not sufficient.** This phase keeps every technical gate as a
floor (§A.2 re-applies the honesty and overflow checks to all three directions). The design itself
is judged against the owner's twelve questions (§10), which no automated metric can answer.

---

## 3. First principles

### 3.A What Archeus is

What Core actually does, from the domain model and state machines (`entities.py`, `states.py`):

| Responsibility | Core object | What the user does with it |
|---|---|---|
| Takes an intent ("Tell Archeus…") and makes it a mission | `Intent` → `Mission` | **delegates** |
| Understands, gathers context, reasons, plans | `UNDERSTANDING … PLANNING`, `ContextPackage`, `Plan` | — |
| Asks its policy; **asks the user** where the policy says ASK | `PolicyDecision`, `Approval` | **decides** |
| Runs the work with coding agents (harnesses) on accounts | `Execution`, `RouteDecision`, `Session` | **oversees** |
| Verifies the result, then asks for acceptance | `Verification.checks`, `Review` | **checks the proof, accepts** |
| Records everything; learns | events, `Checkpoint`, `KnowledgeItem` | **reviews history** |
| Can be stopped at once; is bounded by policy and budgets | the e-stop sentinel, `PolicyRule`, `ResourcePolicy` | **intervenes** |

**What a newcomer must understand within five seconds.** This is the information hierarchy, with
wording left open:

1. This is a system that **does work for me** (agents, missions), and right now it is
   **doing / not doing** something.
2. It **needs me** or it does not, and if it does, **for what** and **by when**.
3. It is **safe**: it is running normally or it is stopped, and I can stop it.
4. It **keeps a record and checks its work**: what was done and what was verified.

Everything else is level two: which project, which branch, which step, which rule, which check.

### 3.B The primary mental model

**Delegation under supervision.** The user hands Archeus missions. Archeus works, stops at the
user's decisions, proves what it did, and can be halted.

The candidate models, evaluated against Archeus's actual responsibilities rather than against
dashboard conventions:

| Candidate primary concept | Fits Archeus because | Fails because | Verdict |
|---|---|---|---|
| **Now / Needs you / Missions** (current LD-2) | Slices the same missions by urgency; good navigation | It is a *navigation* model, not a *product* model. None of the three places represents safety or proof, and "Now" presents everything as rows of one form. It is not a problem of the three tabs; it is a problem of what the first screen is built from | Keep as navigation; not sufficient as the model |
| **Live supervision** (what is happening) | Agents running is the most "alive" fact | Most of the time nothing is running; the model goes empty when the product is quiet | Part of the model (missions in motion) |
| **Attention / decisions** | The user's only mandatory part | A product that is only an inbox hides the work it is doing | Part of the model (decisions) |
| **Missions / work history** | The mission is Core's central object; everything links to it | On its own it buries the urgent (decisions) among the many | Part of the model (the object) — direction B tests it as primary |
| **System / safety state** | It frames every action; the e-stop is a product promise | It is a state, not a place; it is rarely the task | The **frame**, never a place |
| **Activity / history** | It is how trust is built (proof) | On its own it is passive | Part of the model (the record) — direction C tests it as primary |
| **Projects / repositories** | The context that tells look-alike missions apart | The user does not delegate to a repository; a project is a filter and a property | **Context**, on every mission; World stays a secondary place |

**Conclusion:** four concepts, one frame. The *frame* is identity and safety. *Decisions* are the
user's part, *missions* are the work, and the *record* is the proof. The three directions put a
different one of the three in front, but all four are present in each: A gives no single concept
primacy, B puts the mission first, and C puts the record first.

### 3.C What the first screen shows, by priority

| Priority | Content | Answers | Shown as |
|---|---|---|---|
| **Frame** (persistent, low volume) | Identity (mark + name); the **safety state in words**; Core connection; the e-stop; Tell Archeus | "what is this", "is it safe", "can I stop it" | a system bar (desktop) or app bar (phone) on every screen |
| **Primary** | One **state sentence**: does it need me, is anything happening; plus the **nearest deadline** or "nothing needs you" | "is it waiting for me", "can I leave it" | Display type (§F), one sentence, never a bare tally |
| **Primary** | **Decisions waiting**: what, why it asks, by when | "what does it need" | cards (objects you act on), opened to decide, never decided from the list |
| **Secondary** | **Missions in motion**: name, step N of M and task, progress, project · branch, elapsed, next | "what is happening" | rows or tiles with a progress figure and a state word |
| **Secondary** | **Problems**: blocked / failed, with the recorded *because* and what Archeus waits for | "is anything blocked" | rows in the blocked tone, with the cause |
| **Tertiary** | **What changed**: since you looked / today, with what was verified | "what changed", "is everything healthy" | a short record and counts |
| **Not on the first screen** | Remote, environment, current operation (not recorded); raw policy strings, IDs, hashes (detail only); usage and cost (Control) | — | — |

When nothing is happening, the first screen still says so on purpose. It states that nothing
needs the user and nothing is running, what Archeus does when told something, and what it
finished today (§9, *idle*).

---

## 4. Desktop information architecture

The common skeleton all three directions share (each fills it differently, §9):

| Region | Content | Rule |
|---|---|---|
| **System bar** (top, full width) | Mark + name · safety state in words · Core connection · Tell Archeus · the e-stop | Present on every screen; becomes the **stop band** when the e-stop is engaged (§8) |
| **Navigation** | Overview · Decisions · Missions · Record · Control (A); a mission list (B); the brief (C) | Places are views over the four concepts; the safety state is never a place |
| **Main** | The state sentence, then zones (A), the lifecycle pipeline (B) or the record (C) | Uses the width: two or three regions at 1,440 px, prose capped at the reading measure |
| **Detail** | A mission page, or a decision as a document with a decision panel | Desktop shows **overview and detail together** where the direction allows (B, C), or a page with persistent context (A) |

Desktop is a **control surface**: simultaneous visibility of what needs me, what runs, and what
happened, with context persistent rather than one level down.

## 5. Mobile information architecture

| Element | Rule |
|---|---|
| **App bar** | Mark + name, a safety dot, Tell (+), and the e-stop (compact at rest, LD-7's placement: on every screen) |
| **Bottom tab bar** | Three or four places with icons over labels, a badge for decisions, and safe-area padding. Native-feeling, not a floating capsule over the content |
| **Home** | A **status card** (the state sentence plus safety), then grouped sections on surfaces: decisions, missions in motion, problems, today |
| **Drill-in** | Overview → mission → decision are **pushed pages** with a back app bar. Back never exits (LD-5) |
| **Decision** | A full page (LD-5) with a **sticky decision area**: the consequence of Approve above a one-row bar of three ≥ 48 px buttons |
| **Stopped** | The app bar becomes the stop band on every screen. Home states what stopped and offers "Resume work…" (PIN) |
| **One-handed** | Primary actions in the bottom third (decision bar, tab bar); destructive and rare ones (stop) at the top, where they are deliberate |

The phone is designed as its own application with the same four concepts. It is not the desktop
narrowed, and the desktop is not the phone widened.

---

## 6. Visual hierarchy principles

These fix the "too minimal" problem with structure, not decoration. They keep V2's accepted
direction: stillness, opaque tonal depth, the thread as the one signature, and §F typography.

| # | Principle | Rule |
|---|---|---|
| VH-1 | **Three registers** | *Statement* (Display 32/38, phone 30/36), *object* (title-2 / body-strong), *fact* (caption, mono for times and counts). Every screen opens with exactly one statement |
| VH-2 | **Labelled zones** | Zones carry small-caps labels with counts ("WAITING FOR YOU · 3"). Structure must be visible at a glance, not inferred from spacing |
| VH-3 | **State is a word** | Word + colour + shape (chip), never a glyph or a colour alone. Core states map to fixed words (Needs approval, Needs review, Running, Verifying, Blocked, Failed, Done, Planning) |
| VH-4 | **Surface by role** | **Cards** for things you act on (decisions), **rows** for things you open (missions), **lines** for things you read (the record). One elevation step per role |
| VH-5 | **Depth is tonal** | `bg → surface-1 → surface-2` and hairlines. No gradients, glass, blur or decorative shadow (V-3) |
| VH-6 | **The thread is the one signature** | Used where it *means* something: lifecycle progress (B), the record line (C), the because chain. Never as ornament (V-1) |
| VH-7 | **Colour is state** | Amber means waiting for you. Red means blocked, failed or the stop. Blue means running. Green means done or passed. Violet means planning. Nothing else is coloured |
| VH-8 | **Numbers are instruments** | Tabular mono for times, durations and counts. A deadline turns amber only inside 15 minutes |
| VH-9 | **Use the canvas** | Desktop composes for 1,440 px with two or three regions; prose stops at the 72 ch measure; no single 760 px column |
| VH-10 | **Quiet is designed** | Empty and idle states explain the product and invite the next action; they are not blank |
| VH-11 | **Depth discloses, never repeats** | Row → card → page. Each depth adds slots of the explanation frame (§7) instead of restating the previous one |
| VH-12 | **Per-device type** | Phone body 15/22 with ≥ 44 px targets; desktop body 13/20 with V1's targets. §F roles unchanged |
| VH-13 | **Icons only where they carry meaning** | Navigation, check results, the state figure. No decorative icons |

## 7. Explainability principles

### 7.1 The explanation frame

Every significant state is explained in the same five slots, at a depth chosen per surface.

| Slot | Question | Source (all recorded or derived — never interpreted) |
|---|---|---|
| **What** | What is this, in words? | `Mission.state`, `Task.title`, step N of M from the plan, `Approval.kind` |
| **Where** | Which work? | project (DR-1 client join) · branch (`Mission.integration_branch`); repository by DR-3's documented rule only |
| **Why** | Why is it in this state? | the matched policy rules in words (`PolicyDecision.matched_rules`); the recorded *because* (two hops at most, LE-2); "you approved at 14:44" (`approval.decided`) |
| **Evidence** | What supports it? | `Verification.checks` (by name, with results), steps finished, checkpoints, "nothing has run yet" |
| **Next** | What happens next, and what can I do? | the next pending task; **each action's consequence from the state machine** (`states.py`); the expiry |
| *Unknown* (decisions) | What does Archeus not know? | the gaps by name: environment (DR-4), remote (DR-2), current operation (DR-6) |

Depth:

| Depth | Slots |
|---|---|
| Row | what + where + one of why or next |
| Card or summary | all five, one line each |
| Page | all five in full, plus the context block and the record |

### 7.2 Rules

- **Consequences come from the state machine, not from prose.** "Approve: Archeus starts *Build
  the site* now, then the other 2 tasks." "Reject: the mission is cancelled; nothing has run."
  "Ask for changes: Archeus re-plans with your note; nothing runs." Each is a `states.py`
  transition plus the plan's task list. It costs no data contract, and it is the single biggest
  trust gain available.
- **Provenance is structural, not literal.** LD-9's rule stays: every clause is traceable to a
  field. The prototype carries it as `data-src` on every fact, and `?prov=1` outlines known,
  derived and not-recorded facts for review. The copy does **not** narrate its own provenance
  ("according to the Verification record…"). Known facts read plainly. Derived facts read plainly
  and state their rule on hover and in the detail. A not-recorded fact is named once per block:
  "environment: not recorded".
- **Two hops, and no interpretation.** A *because* chain stops at the last recorded fact (the
  failed check). It never adds a model's reading of the output.
- **The deadline is a fact with a consequence.** "Expires 15:20 (in 8 min). If nobody decides,
  the approval expires and nothing runs" (`authorization.expire_due`).
- **Plain state names.** Core's state names map to fixed words (VH-3). Policy rule strings appear
  only in a decision's detail, in mono, after the plain reason.
- **Say what is not known, once.** On a decision: "What Archeus does not know: environment, remote."
  Never a placeholder per field, and never a guessed value.

## 8. Safety-state presentation rules

### 8.1 The "armed" collision, as found in the code

The ambiguity the owner names is real. It is already present in **opposite senses inside one
codebase**:

| Where | Text | "Armed" means |
|---|---|---|
| V1 UI copy (P20, `clients/app/src/state/present.ts:361`) | "Armed: Archeus accepts new work." | **running normally** |
| Core (`archeus/core/application/authorization.py:99`) | `estop_armed()` is true when the STOP sentinel exists | **stopped** |
| Core policy reason (`archeus/core/policy/engine.py:123`) | "emergency stop armed: every action is denied" — stored as `PolicyDecision.reason` | **stopped** |
| LD-7 as approved | "the first press arms, the second stops" | **one press from stopping** |

So one word carries three meanings, and one of them, the policy reason, is a recorded string that
can reach a screen.

### 8.2 Rules

| # | Rule |
|---|---|
| SS-1 | **The safety state is always visible, as its meaning.** It reads "Working normally · accepts new work", "Emergency stop · new work refused", or "Core cannot be reached · state not known". It is never "armed" or "disarmed" |
| SS-2 | **"Stop" and "stopped" belong to the emergency stop only.** Mission problems are *Blocked* or *Failed*, the Core state names. (The current Now headline "2 stopped" breaks this, X-3) |
| SS-3 | **At rest, the e-stop is present but quiet.** An outlined control in stop ink, labelled "Stop all work" ("Stop" on the phone app bar). It is not the loudest object on the screen (X-4) |
| SS-4 | **The primed state is unmistakable without the word "armed".** After the first press the control fills with the stop colour and reads "Press again to stop all work". A countdown bar shows the 3 s lapse. A hint states exactly what the second press does: how many missions stop, that new work is refused, that the stop lapses if nothing is pressed, and that resuming needs a PIN. In forced colours it is distinct by text and shape |
| SS-5 | **The stopped state changes the whole frame.** The system or app bar becomes a stop band on every screen. It says when the stop happened and from which device ("All work stopped at 15:14 from this computer. New work is refused."), what was stopped, what is held ("3 decisions are still open; nothing they allow can run until you resume"), and the way back |
| SS-6 | **The way back is "Resume work…".** It needs PIN step-up (P20 D10, unchanged). The word "re-arm" is not used on V2 surfaces |
| SS-7 | **No dialog, and no timer that acts on the user's behalf** except the lapse back to safe (primed → rest) |
| SS-8 | **The semantics do not change.** LD-7's interaction stands as approved: two presses, a 3 s lapse, no dialog, re-arm through P20's step-up, and the automated coverage. Only the words change. Any change to the semantics needs a new gate |
| SS-9 | **Calm, not an emergency console.** The stop is one control in the frame. The safety state is a calm word in normal operation and is loud only when the stop is engaged |

**Open for the owner (Q3):** V1's own copy (`armedText`) and Core's recorded policy reason belong
to P20 and Core. This document does not change them. It proposes recording them as a P20
follow-up item (§13).

**To verify against Core before production copy (not a data contract):**

- Whether an approval can still be *decided* while the e-stop is engaged. The policy engine denies
  every action (`engine.py:123`), and expiry keeps sweeping. The prototypes therefore say only
  "nothing they allow can run until you resume".
- What resuming does to the missions the stop blocked. Core blocks them (`executions.py:410-425`),
  and the state machine's exits from BLOCKED are *unblock* and *cancel*. The prototypes say "stays
  blocked until you resume Archeus and unblock it".

---

## 9. Three design directions

All three are built on the same model, fixture, honesty rules, e-stop component, §F typography
and V1 tokens. The difference is which concept leads the first screen and how the product is
organised around it. **These are different products, not three themes.**

Captures: `results/lvx/{a,b,c}_{desk,phone}_{home,live,decide,mission,primed,stopped,idle}.png`.
The phone has full-page `_full` captures for home, live and decide. A side-by-side review page is
at `lvx/gallery.html`.

| State | Fixture |
|---|---|
| Opening (`home`) | 3 decisions, 2 running, 1 blocked, 1 failed, 1 planning, 2 done |
| Running mission (`live`) | *Fix the flaky date test*, step 4 of 7 |
| Approval (`decide`) | Plan v2 for *Deploy release notes to staging*, expires in 8 min |
| Mission detail (`mission`) | *Write the migration for invoices*, blocked: the rollback check failed |
| E-stop primed (`primed`) | The first press |
| Emergency stop (`stopped`) | Engaged at 15:14 from this computer |
| Idle (`idle`) | Nothing running, nothing waiting |

### 9.A Direction A — Supervision desk

**Idea.** Archeus is the desk you supervise delegated work from. The opening screen answers the
supervisor's questions in **fixed zones that never move**, in priority order: is it safe → what
needs me → what is running → what went wrong → what happened today.

| | Desktop | Phone |
|---|---|---|
| Frame | System bar: mark and name, safety state in words with "Core connected", Tell field, e-stop. Left nav: Overview · Decisions · Missions · Record · Control, plus Projects with active counts | App bar: mark and name, safety dot, +, Stop. Bottom tabs: Overview · Decisions · Missions · Record |
| Opening | Statement ("3 decisions are waiting for you."), counts, **next deadline**. Four framed zones: Waiting for you (decision cards, opened only through *Review*) · Running now (step bar, step N of M, project · branch, elapsed, *Then:*) · Needs attention (because + next) · Today (stat strip + recent record) | A status card (statement, counts, safety), then the same zones as stacked cards |
| Decision | A labelled document (what you approve, why Archeus asks with the rule strings, what changed, your request, context with the gaps) and a **sticky "Your decision" panel**: each button with its consequence, the expiry, "Closing this page decides nothing" | Full page; the Approve consequence above a one-row bar of three |
| Mission | Big step bar and step list; *Right now* / *Context* / *Record* panels; when blocked, a "Why it is blocked" thread, the checks, the DR-8 gap, and the actions with their consequences | Full page with the same sections |
| Stopped | The system bar becomes the stop band ("EMERGENCY STOP · All work stopped at 15:14 from this computer. New work is refused." with *Resume work…*). "Archeus is stopped." The running zone becomes "Stopped by the emergency stop" | The app bar becomes the band; the status card states the stop, with a large *Resume work…* |
| Idle | "Nothing needs you, and nothing is running." A paragraph on what Archeus is, a large Tell field, a *Right now* strip of explicit empties, Today, and a five-step **How Archeus works** | The same, stacked |

**Strengths.** It is the fastest of the three at a glance and the strongest *control surface*.
The safety state and the next deadline are always in view, and nothing is decided from a list.
On a phone it is a recognisable, competent application.

**Weaknesses.** It is the most dashboard-like and the densest when busy. Its identity is weak: it
could be any well-made operations product. It teaches what Archeus *is* only when idle.

### 9.B Direction B — Mission lines

**Idea.** The **mission** is the object. Decisions, verification and the record are moments on
its **mission line**: the six phases of Core's state machine (Understand · Plan · Approve · Run
· Verify · Review), drawn as a fine line. Past phases are ivory, the current one is lit in its
state colour, future ones are faint. This is V1's thread made structural. It is the one
signature, and V2-U1 already plans it as the spine primitive with its own ADR.

| | Desktop | Phone |
|---|---|---|
| Frame | Top bar: mark and name, safety state, Tell, e-stop | App bar: mark and name, safety dot, +, Stop. Bottom tabs: Missions · Record · Control |
| Opening | Left: the mission list grouped Waiting for you / In progress / Blocked or failed / Done today, each with a mini line. Right: the statement ("3 missions wait for you at Approve and Review."), the next deadline, and the **pipeline**: six phase columns, each saying what Archeus does there (and "ASKS YOU" under Approve and Review), with every open mission placed in its phase. Below: Done today (with checks) and Since you looked | A summary (statement, safety, three counters), then mission cards, each with a full-width line and the phase name lit |
| Decision | The list stays. Right: the mission page, with the line's **Approve node lit amber, "waiting for you · expires 15:20"**. Under it the explanation (what you approve, why Archeus asks, what changed, your request) and the decision card with each consequence | The mission page with a vertical spine; the decision in place; a sticky one-row bar |
| Mission | The line with the current phase expanded: Run into its seven steps; Verify into its checks, the because chain, the DR-8 gap and the actions | **A vertical spine** down the page: phases as a timeline, the current one expanded with its steps and the explanation frame |
| Stopped | A stop band under the bar; *Tell* gives way to *Resume work…*. "All work is stopped." The two stopped missions carry a stop mark on their Run node and lead the list as "Stopped by you" | The band, the summary, *Resume work…* |
| Idle | "Nothing needs you, and nothing is running." What Archeus does, a large Tell field, **How a mission moves** (the empty line with each phase explained), Done today, Last activity | The same, stacked |

**Strengths.** It has the strongest identity: no other product draws work on its own lifecycle.
It answers *what is Archeus* even when busy, because the pipeline **is** the explanation of how
it works. It is the best at telling missions, projects and branches apart. A decision is shown
*where it sits in the work*, which makes "why am I being asked, and what happens next" visible
rather than written out. The phone's vertical spine is the most native-feeling page of the three.

**Weaknesses.** Verification and recent activity are tertiary, below the pipeline and off the
first screen when busy. Decisions are not a separate place, so their count leads only through
the statement and the list's first group. The pipeline is dense, and at scale (twenty open
missions) it needs a per-column cap; that is untested. The Understand column is usually empty.

### 9.C Direction C — Brief & record

**Idea.** Archeus reports like a trusted colleague. A short **brief** of sentences, each a
template over recorded facts, sits beside the **record** (a fine thread through the day). An
always-present **evidence** pane shows, for whatever is selected, what is known, what is derived
and what is not recorded.

| | Desktop | Phone |
|---|---|---|
| Frame | Top bar: mark and name, safety state, Tell, e-stop | App bar plus a slim safety line. Bottom tabs: Brief · Record · Missions |
| Opening | Three panes. **Brief**: "Archeus needs 3 decisions from you." plus four fact sentences (running, blocked/failed, verified today, since you looked), then the decisions phrased as questions. **Record**: live missions pinned with step bars, then the day's events grouped by mission with verification chips. **Evidence**: the what · where · why · evidence · next frame, the context, and a legend of the three kinds | A brief card, question cards, Now cards, the Today timeline |
| Decision | Centre: a **question-and-answer document** (what are you approving · what happens next · why is Archeus asking · what changed · what did you ask for · what Archeus does not know) with a pinned bar. Right: the policy rules and the context | Full page with the same Q&A; a sticky one-row bar |
| Mission | Centre: "why this mission is blocked" on the record line, the actions, the checks with the DR-8 gap, and the mission's record. Right: the evidence | Full page, with the evidence frame inline |
| Stopped | The stop band; "You stopped all work at 15:14." with what was halted, what is held ("every action is denied while stopped") and *Resume work…*; the record leads with the stop | The band, the brief, *Resume work…* |
| Idle | "All quiet." What Archeus does, today's summary, a large Tell field; the record of today's finished work | The same |

**Strengths.** It is the best at *why*, *what was verified* and *what happened*. The evidence pane
and the Q&A decision are the most trustworthy surfaces of the three. A newcomer can read the
brief aloud and understand the product.

**Weaknesses.** It is the wordiest and the slowest to scan. The desktop reads like a reading room
rather than a control surface. The brief is prose, so every new sentence is a new chance to
assert something Core does not record, and its honesty depends on discipline that is hard to
keep at scale. On the stopped screen the resume action appears twice.

## 10. Comparison matrix

**This is design-review judgement (1–5), not measurement.** No human was asked (W2 skipped by
owner decision), and no automated metric can answer these questions. The automated check (§A.2)
is a floor that all three pass equally, so it does not separate them.

| # | Question | A · Supervision desk | B · Mission lines | C · Brief & record |
|---|---|---|---|---|
| 1 | Can a new user explain what Archeus is? | 3 (5 idle: *How Archeus works*) | **4** (the pipeline teaches the phases while busy too) | **4** (the brief and *What Archeus does*) |
| 2 | Can they tell what is happening now? | **5** | 4 | 4 |
| 3 | Can they tell whether Archeus needs them? | **5** | 4 | **5** |
| 4 | Do they understand why something needs approval? | 4 | **5** (the decision sits on the lifecycle) | **5** (Q&A + evidence) |
| 5 | Can they identify the mission, project and branch? | 4 | **5** | 4 |
| 6 | Can they tell what was verified? | 4 | 3 | **5** |
| 7 | Can they tell what Archeus did recently? | 4 | 3 | **5** |
| 8 | Do they understand the safety state? | **5** | 4 | 4 |
| 9 | Does mobile feel like a real application? | 4 | **5** (the vertical spine) | 4 |
| 10 | Does desktop feel like a control surface, not a stretched phone? | **5** | 4 | 3 |
| 11 | Does the interface remain minimal? | 3 (the most chrome) | 3 (the pipeline is dense) | 3 (the most words) |
| 12 | Does it have enough identity to feel like a product? | 3 | **5** | 4 |

The sums are within one point of each other (A 49, B 49, C 50), so **the matrix does not pick a
winner by itself**. The decision turns on which weaknesses can be fixed by *adding* to a
direction, and which are built into its structure:

| | Structural weakness (hard to fix without becoming another direction) | Additive weakness (fixed by adding a part) |
|---|---|---|
| A | Identity: a zoned dashboard is a dashboard | — |
| B | — | Verification and recent activity: a Record place and the Verify phase's checks on the home |
| C | Scanning speed and desktop "reading room"; prose as an honesty risk at scale | — |

## 11. Recommendation

**Direction B, Mission lines, as the base.** Two parts are borrowed by explicit rule:

1. **From A, the frame and the deadline.** A's system bar is B's already: the safety state in
   words, "Core connected", and the stop band. A's **next-deadline line** is also already in B.
   B takes A's **Today stat strip** (done · checks passed · checks failed) under the pipeline, and
   A's rule that **nothing is decided from a list**.
2. **From C, the evidence and the Q&A.** C's **evidence presentation**: the frame as labelled rows
   with the known / derived / not-recorded legend. It becomes the detail column of B's mission
   page. C's **"What Archeus does not know"** goes on every decision. C's **Record** becomes B's
   second tab, a place that reads as C's record line (which needs DR-7 for a calendar day).

**Why B.**

- **It answers the owner's actual complaint.** The owner wants identity, explanation and
  hierarchy without noise. B is the only direction whose identity *is* its explanation: the line
  shows how Archeus works on every screen, and the signature cannot become decoration because it
  only ever draws a recorded state.
- **It is the model in §3.** The mission is the object. A decision is a moment on it. The proof
  belongs to its Verify phase. The frame carries the safety state.
- **It is built from what Core already is.** The line is a projection of `states.py`, and V2-U1
  already plans the spine primitive and its ADR. Nothing in it needs a new data contract.
- **Its weaknesses are additive.** The two borrowings above fix them. A's identity problem and
  C's scanning problem are not additive.
- **Mobile and desktop are each native to their size.** Desktop gets the list and the
  pipeline/detail side by side. Phone gets the vertical spine.

**The runner-up is A.** If the pipeline does not hold up at scale (the LV2-X.2 stress test with
twenty open missions), A is the safer control surface. In that case, B's mission line still
belongs on A's running tiles and mission pages.

**What this recommendation does not claim.** It is not validated by anyone but this review. It
does not prove that B's pipeline scales (untested) or that the lit line reads in Qt exactly as in
Chromium (untested). It does not claim that any of the three is better than the LV2-1 prototype
for real users. The owner judges the captures.

---

## 12. Data contracts the directions need (none implemented)

| Need | Where it appears | Contract | State today | Prototype behaviour |
|---|---|---|---|---|
| Project name on every mission, decision and record row | all directions, every screen | **DR-1** (option A: client join on `/v1/projects`, no Core change) | draft | rendered as known through the client join |
| A mission's repository in a multi-repository project | context blocks (`invoicing`) | **DR-3** | draft | "repository: not recorded · requires DR-3"; one-repository projects use DR-3's documented derivation |
| Remote / provider / owner-repo | context blocks; the decision's "does not know" | **DR-2** (credentials stripped) | draft | "remote: not recorded · requires DR-2" |
| The target environment of a deploy | the decision's "does not know" | **DR-4** | draft | "environment: not recorded · requires DR-4"; never "deploys to staging" |
| The current operation inside a running task | the live mission's *what* slot | **DR-6** (P21's activity record) | owned by P21 | "current operation: not recorded · requires DR-6" |
| A day-scoped record ("Today") | A's Today zone, C's record pane, every idle screen | **DR-7** | not drafted | the fixture's day. **In production today**, `/v1/events` has only `after` and `limit`. "Since you looked" is fully supported (`User.last_ack_event_seq` + `after`), but a calendar-day record needs DR-7 or client-side paging |
| A failed check's output | the blocked mission's evidence | **DR-8** (with P20's secrets review) | draft | "check output: kept by Core, not readable here · requires DR-8" |
| Row status line and live-work fields | every running row | **DR-5** = V1 defects V-1, V-2 (§13) | V1 defect | rendered from the fixture's `LiveItem` shape |
| Each action's consequence | every decision | none: `states.py` transitions + `Plan.tasks` | known | derived, with the transition named in `data-src` |
| Why a decision is asked | every decision | none: `PolicyDecision.matched_rules` | known | derived in words; the rule strings in mono in the detail |
| The lifecycle phase of a mission | B's mission line, every direction's state word | none: client mapping generated from `states.py` (V2-U1's planned spine ADR) | planned | client mapping in `lvx/data.js` |

**No new contract is invented by this phase.** DR-7 already exists (LE-2 §3) but has no drafted
gate. It is the one the record-forward directions (A's Today zone, C's record) depend on for a
calendar day.

## 13. The V1 relationship: the minimum before V2 depends on it

V2 exploration is not a reason to redesign V1. The minimum V1 defects V2 depends on stay in V1's
own gate, for P20's follow-up or before P26, unchanged from the LV2-2 plan's Q2:

| # | Defect | Where | Fix lives in |
|---|---|---|---|
| V-1 | Rows call `statusLine(m)` without tasks, so the row status line is **always empty** on Now and Work | `present.ts:149-152`, `Work.tsx:107` | V1 follow-up |
| V-2 | `LiveItem.workdir`, `branch`, `task_title` and `waits_on` are missing from the generated TS type, and the last two are fetched and never shown | `generated.ts`, `live.py:60-80` | V1 follow-up |
| V-3 | The project name never reaches a mission, decision or digest row (DR-1 option A is client-only) | the client's reads | V1 follow-up or V2-U1 |
| V-4 *(new, recorded only)* | Core's recorded policy reason says "emergency stop **armed**" for *stopped*, while P20's copy says "**Armed**: accepts new work" for *running* (§8.1) | `engine.py:123`, `present.ts:361` | **P20's** vocabulary decision (Q3); not changed here |

## 14. Existing decisions: valid, candidate, or reconsider

This is a **proposal**. The recorded decisions stand until the owner changes them.

| Decision | As recorded | Proposed status | Why |
|---|---|---|---|
| **LD-1** budget ≈ 12.5 KB | decided | **Valid as a cap**, re-measured on the chosen direction | A richer IA costs markup; the cap stays and the direction is priced in-bundle (D-4) |
| **LD-2** three places + phone IA | approved (no human validation) | **Reconsider** | A navigation model, not a product model (§3.B). All three directions add *Record* as a place, or make it primary, and change what the first screen is built from |
| **LD-3** fold the Now rebuild, approval screen, plain labels and visible verification into V2 | approved | **Valid as scope**; the *Now rebuild's shape* becomes a candidate | The four outcomes are exactly what §3–§7 require; the LV2-1 shape of Now is what §2 diagnoses |
| **LD-4** the day's light | open | **Open**, unchanged | — |
| **LD-5** phone decision is a full page | approved | **Valid** | All three directions keep it; it is what makes the explanation frame fit on a phone |
| **LD-6**, **LD-10** | deferred | Deferred, unchanged | — |
| **LD-7** two-press e-stop | approved | **Valid semantics; wording rule added** (SS-4, SS-6) | "Arms" leaves the copy. The interaction, lapse, coverage and PIN re-arm are unchanged |
| **LD-8** no warm grey | decided | **Valid** | — |
| **LD-9** the honest record, every clause traceable | approved | **Valid principle; delivery reframed** as the explanation frame (§7) | Traceability is kept structurally; literal provenance language is not forced |
| **D-1** rows carry project · branch; no remote, operation or environment | approved | **Valid as the data rule**; the row's *shape* is a candidate | Every direction keeps `pb` and the not-shown facts; how the line sits in a row differs |
| **D-2** V1 names (Now, Attention, Work) | approved ("for now") | **Reconsider** | The places themselves change. A and C introduce *Decisions* and *Record*, and B makes Missions primary. The names follow the chosen model (Q2) |
| **D-3**, **D-4**, **D-6** | decided | Valid, unchanged | — |
| **D-5** LE8 presentation target; one-row bar; 20 px headers; §F default | approved | **Candidate** | §F and the one-row phone bar are kept in all three directions. The rest of LE8 was a pass over a structure §2 diagnoses, so it is re-derived for the chosen direction |
| **§F typography** (V2-U0) | decided | **Valid** | All three directions use it |
| DR-1/2/3/4/8 | drafts | **Valid as gates**, unchanged | — |
| **LV2-2 plan** | proposed, not authorised | **On hold**; to be re-planned on the chosen direction | Its slices S1/S2/S8 assume LD-2's Now and D-5's pass. S3–S7 and S9 survive in substance (decision surface, language, verification, context, e-stop, data) |
| The V2-U0 human gates (PR-5, PR-3; later PR-1, PR-6) | accepted conditions | Unchanged; still the LV2-2 plan's open Q1 | Not waived by anything here |

## 15. Revised roadmap: what happens before LV2-2

| Step | Content | Exit |
|---|---|---|
| **LV2-X.0** (this document) | Diagnosis, model, IA, principles, three directions, comparison, recommendation | The owner's review |
| **LV2-X.1** — choose | The owner picks a direction, or a combination with an explicit rule for each borrowed part; answers Q1–Q6 (§16) | Recorded decision |
| **LV2-X.2** — refine the chosen direction | All remaining states (loading, Core unreachable, light theme, forced colours, 200 % text, reduced motion); the stress corpus and look-alike days; **Qt = Chromium** on every layout fact; a replay of **real V1 Core data** (ADR-0029 captures) to prove every fact is known or derived; a structured design review against the twelve questions; a measured in-bundle estimate (LD-1) | Every state shot and reviewed; honesty and overflow checks green; the owner's sign-off. **No human study by default.** If the owner's review and the design review disagree on a question, one small focused check (for example a five-second test with three people) answers that question only |
| **LV2-2 re-planned** | The LV2-2 plan rewritten on the chosen direction, keeping its surviving slices (decision surface, language, verification, context, e-stop, data) | The owner's authorisation |
| Unchanged dependencies | P26 before any V2 production; V2-U1 (tokens v2; the spine ADR, which B makes central); V-1/V-2/V-3 in V1's follow-up; the V2-U0 human gates as recorded until the owner decides (LV2-2 plan Q1) | — |

## 16. Questions for the owner

| # | Question | Recommendation |
|---|---|---|
| Q1 | Which direction, or which combination (§11)? | B as the base, with the two borrowings named in §11; A as the fallback if the pipeline fails the scale test |
| Q2 | The places' names: keep V1's (D-2), or name them after the model (e.g. Overview · Decisions · Missions · Record)? | Name them after the chosen model; decide in LV2-X.1 |
| Q3 | "Armed" in V1: change P20's copy and Core's recorded reason (a P20 follow-up), or leave V1 as it is and keep the word off V2's surfaces only? | Record V-4 as a P20 follow-up; V2 never shows the word either way |
| Q4 | Is *Record* a first-class place? A calendar-day record needs DR-7 | Yes, if A or C is chosen; draft DR-7's gate in LV2-X.2 |
| Q5 | Is "Tell Archeus" a primary action on the opening screen (it is how missions start), or a secondary one? | Primary when idle, secondary otherwise (as prototyped) |
| Q6 | The LV2-2 plan's Q1–Q6 remain open; re-ask them after the direction is chosen? | Yes |

## 17. LV2-X.1 — the owner's review, and Direction D

The owner reviewed the 42 captures on 2026-10-06 and chose a **combination**, with a rule for each borrowed
part. It is built as a fourth prototype, **D · Synthesis** (`?d=d`, `lvx/d.js`, `lvx/d.css`;
`gallery.html?set=d`). A, B and C are unchanged as evidence. §9–§11 stand as written: they record what was
proposed before this review, and nothing above was edited to agree with it.

### 17.1 What the owner decided

| Part | Decision | Taken from |
|---|---|---|
| Structure | Sections and pages with a left bar, navigable like a normal application. Places: **Overview · Missions · Projects · Control**, on both desktop and phone | A |
| Mission lines | Kept as a collapsible list in the left bar, so it is always visible what is running and how far along it is | B |
| Desktop overview | Waiting for you (each with a *Review* button) first, then errors, then Running now, then the rest | A |
| Progress | The connected-dot mission line is the one progress element everywhere. Completed phases are **green ticks**; a failed phase is a **red cross** | B's shape, A's colours |
| Mission page | One page per mission on which every state happens. Back button, title, state, project and branch at the top. A decision or a problem **appears as a component under the line** and pushes the rest down | A's head, B's page |
| Activity | A terminal-style log under the page showing the work as it happens | new |
| Approval (desktop) | What you approve, why Archeus asks, and three buttons on the right: **Approve filled at the top**, the others outlined below | B |
| Approval (phone) | The same component. Buttons in one row: **Reject** (red outline, left), **Change** (outline, centre), **Approve** (filled, right) | new |
| After Approve | The component disappears and the page is as before. The line shows **"Approved ✓"**. Clicking it opens a side panel with what was approved, when, and every earlier answer and instruction | new |
| Error | The same page in red, with the failed phase crossed. Three actions: **Explain the error** (asks the agent that ran it; a loading state, then the answer written letter by letter), **Ask Archeus to fix it** (with your instructions), **Cancel mission** | B's page, A's component |
| E-stop pressed once (desktop) | A: red across the whole window | A |
| E-stop pressed once (phone) | B's banner | B |
| Emergency stopped | A | A |
| Idle | An invitation to work: no "Nothing needs you" or "All quiet", just one bright **Tell Archeus what to do** | B's button |
| Phone overview | B's three counters (Waiting · Running · Blocked or failed), then A's Waiting-for-you cards, then errors, running, and the projects | A + B |
| Phone mission | Its own page with a back button and **no tab bar**; a horizontal line styled like B's | A + B |

### 17.2 How D applies it, and where it had to choose

- **The line is phases, not tasks.** The owner asked for the dot line "for the steps". D draws the six
  phases of `states.py` on the line and the plan's tasks as the green-ticked list under it. Two reasons:
  - "Approved ✓" and "the failed step crossed" are phase events.
  - A task line would have a different length on every mission.

  The Run phase's caption still reads "step 4 of 7".
- **Error, desktop.** The owner placed the three buttons "in the next section" after the logs. D puts the
  *why* and the buttons in the component under the line, the same place and shape as the approval
  component, with the terminal below it. On the phone the owner asked for exactly this, so desktop and phone
  now agree. **Owner to confirm (Q7).**
- **Reject is outlined in red on desktop too.** This matches the phone spec, so one button means one colour.
- **Decisions and Record are no longer places.** Decisions live on the overview and on their mission. The
  record is each mission's activity plus the decision side panel. C's whole-day Record is not built (it
  would need DR-7). **Owner to confirm (Q8).**
- **"Explain the error" is the primary of the three.** It is the only one that changes nothing.
- **Letter-by-letter answer.** In production this is the agent's own stream arriving, not a typewriter
  effect over finished text. A capture shows it whole; reduced motion shows it at once. The loading dots
  animate opacity only, and freeze in captures and under reduced motion.

### 17.3 What the new parts need from Core

| Part | Status in Core | Mark on screen |
|---|---|---|
| Activity terminal | **Exists.** `GET /v1/executions/{id}/stream` (P16 D4) carries the agent's text, each tool call with its input, tool ok/error, and the result, all redacted. It does **not** carry tool output, and its events have no times. Core events (`…/timeline`) carry the times | Known. Header: "Tool output is not in the stream." A failed check's output is DR-8 |
| "Approved ✓" side panel | **Exists.** `approval.decided` (decision, actor, time), the Approval (plan version, matched rules), and the reason that `request_changes` requires | Known |
| Cancel mission | **Exists.** `commands.cancel`: BLOCKED / FAILED / PAUSED → CANCELLED | Known consequence |
| Ask Archeus to fix it | **Partly.** `commands.resume` unblocks and redispatches, and records a `reason`. Nothing shows that the reason reaches the agent. For FAILED, the edge is `replan` | Consequence known; "your instructions reaching the agent" is **requires DR-9** |
| Explain the error | **Does not exist.** Core cannot put a question to a mission's agent and stream back the answer. The prototype's answer is sample text | **requires DR-9** |

**DR-9 (new, not drafted): a message to a mission's agent.** It is one channel with two uses: a
question that changes nothing (Explain), and instructions carried into the next run (Fix). It needs:
- the harness session to resume (`provider_session_ref`, the handoff machinery);
- the answer to come back through the same redacted stream;
- policy for what the agent may do while it answers. Explain must be read-only.

Like the other DR gates, it stays out of V1/P20.

### 17.4 Results

- **D: 28 of 28 captures pass** (`results/lvx/check_d.txt`): 14 states × desktop and phone, plus full-page phone captures of home, live, approval, after-approve and error.
- **The gate failed first and the defects were real:**
  - two tap targets under 44 px on the phone ("Approved ✓", and the idle "done today" link);
  - a Control page with 3 facts.

  Both were fixed, not exempted.
- **Idle is held to a floor of 1 fact, not 6.** This is the one deliberate change to the gate: you asked for the empty overview to be a single invitation.
- **A small change to the shared model** (`data.js`):
  - a `?did=approve` scenario moves the mission through the state machine's own edge (APPROVAL_REQUIRED → approve → APPROVED → dispatch);
  - *Right now* no longer assumes a checkpoint exists;
  - "You approved the plan at…" now reads the approving decision, not the first decision. For a mission sent back once (m-91d2) the first one is the request for changes, so it would have shown the wrong time.

  A, B and C were re-captured after this change.
- **Not yet done** (LV2-X.2):
  - motion: the thread travelling along the line on a phase change;
  - the remaining states: loading, Core unreachable, light theme, 200 % text;
  - the stress corpus;
  - Qt = Chromium.

### 17.5 Roadmap

LV2-X.1 is **recorded, pending Q7–Q8**. LV2-X.2 refines D, not B: the roadmap in §15 otherwise stands. LV2-2
is still not authorised.

**Questions added.**
- **Q7.** On the error page, desktop: should the *why* and the three actions sit in the component under the line (as built, matching the phone), or after the activity log?
- **Q8.** Are Decisions and Record no longer places (as built)? Or should Record come back as a fifth place, which would need DR-7?
- **Q9.** Should DR-9 be drafted as a gate now, so Explain and Fix can be planned? Or should both ship first as their honest subsets: Fix as *unblock and run again*, with your note recorded but not passed on, and Explain held back?

## 18. The owner's second review, and Direction E

The owner reviewed D on 2026-10-06 and asked for a fifth view, **E**. It is built on D's module
behind a variant flag (`?d=e`, shared `d.js`, own `e.css`; `gallery.html` opens on E). **D is unchanged as
evidence: all 33 of its captures are byte-identical before and after E was added.** §17 stands as written.

### 18.1 What the owner decided

| Part | Decision |
|---|---|
| Desktop left bar | The **projects are always visible** there. The mission lines (dots and dashes) leave the bar and stay on the Missions page, as they were |
| Places | **Overview · Missions · Ideas · Projects · Control**, on desktop and phone |
| Phone approval | The three answers are **fixed at the bottom of the screen and always visible**: Reject (left), Changes (centre), Approve (right) |
| Idle | D removed too much. Tell Archeus what to do stays first, but the page also shows **what was done and the projects**. What was wanted was fewer words, not an empty page |
| Buttons | **No caption under any button, anywhere.** The buttons speak for themselves. This is a general rule for the whole product |
| Project page | Opening a project shows its **timeboard**: B's phase columns with each of the project's missions where it stands. Then every detail Core has about the project |
| Ideas (new) | A big central button for an idea for a **new project**. Next to it, one that records the idea and **starts implementing it**. Below, every project with its own button for a new idea for that project. Archeus then researches how to implement it (branch, plan). For each project, its ideas can be changed or started, and starting one creates a mission |

### 18.2 How E applies it

- **Consequences become tooltips.** The consequence of each answer (derived from `states.py`, as before)
  is no longer printed. It becomes the button's `title` (hover on desktop). The explanation stays on hand
  without being on screen.
  - **Kept:** the expiry ("Expires 15:20 · in 8 min"), because it is a fact about the decision, not a
    caption on a button.
  - **Kept:** the e-stop's primed band, which is the SS safety copy. Removing it would change the safety
    presentation without a gate (§8).
  - **Gone:** the Control page's explanatory sentence.
- **Projects in the bar:** the open project is selected. On a mission's page, its project is only marked, so
  that two places never look selected at once.
- **The phone decision bar** also carries a result review (Changes · Accept). The component above it keeps
  what, why, what changed and the expiry.
- **Gaps are tags, not sentences.** A capability that Core lacks is a small dashed tag on the thing that
  needs it (for example "research · requires DR-10"), with the detail in its tooltip.

### 18.3 What Ideas and the project page need from Core

| Part | Status in Core | On screen |
|---|---|---|
| The ideas, per project | **Exists.** `Idea` (text, title, optional `project_id`, state), `GET /v1/ideas`, `idea.created` | Known |
| Start an idea | **Exists.** The conversation's promote: the idea moves to IMPLEMENTING, and a mission is created with `origin: idea` and the idea's project. The idea then follows its mission to COMPLETED (`conversation.py`) | Known; the tooltip says so |
| Capture with a button | **Partly.** An idea is captured today only when the brain reads a Tell message as one. A direct capture command does not exist | Tag: direct capture · requires DR-10 |
| Archeus researches the idea | **Does not exist.** The idea state machine has EXPLORED and VALIDATED, but nothing fires `explore` | Tag: research · requires DR-10 |
| Change an idea | **Does not exist.** Core keeps an idea's text as captured | Tag: editing · requires DR-10 |
| Project page | **Exists**, as client joins: `Project`, its `Repository` rows (path, default branch, last revision), its missions and their events. The remote is DR-2 | Known; remote is DR-2 |

**DR-10 (new, not drafted): ideas beyond capture-by-conversation and promote.** It covers:
- a direct capture command;
- a research pass that moves an idea to EXPLORED, with a recorded result (a proposed branch and a plan
  sketch);
- editing a captured idea.

Like DR-9, it stays out of V1/P20.

The idea fixture (five ideas, one promoted into m-5c30) is synthetic and local to the prototype, like the
rest of the fixture.

### 18.4 Results

- **E: 36 of 36 captures pass** (`results/lvx/check_de.txt`), and **idle is held to the normal floor of 6
  facts.** E's idle is no longer near-empty, so it gets no exemption.
- **The gate did not catch one defect, and review did:** the project page's two-column grid did not
  collapse on the phone, so Ideas and Details were squeezed into a thin column. Nothing overflowed sideways,
  which is all the gate measures. It is fixed. A check for a too-narrow column is a candidate for LV2-X.2.
- **D re-captured and byte-identical** (33 of 33).

### 18.5 Roadmap

LV2-X.2 now refines **E**. The rest of §15 stands, and LV2-2 is still not authorised.

**Q7–Q9 (§17.5) are still open. Question added.**
- **Q10.** Should DR-10 be drafted now? Or should Ideas ship first as their honest subset: the list, start
  (promote) and capture through Tell, with the direct button, research and editing held back?

### 18.6 Third review: the idea page

The owner accepted E ("così ci sta") and asked for four changes, all applied to E:

| Asked | Applied |
|---|---|
| New idea as a **popup in the middle**, not a side panel, on the desktop and the phone | A centred dialog over a dimmed page. "Change" opens it too |
| **Change / Start smaller, at the side** on the phone: with two or more ideas per project it was chaotic | Compact buttons beside each row (32 px tall, the floor of the tap-target rule for a wide control). An idea already in a mission stacks its mission link under the title |
| A **Research** button that works out the idea and how to build it | On the idea page: *Research* when there is no plan, *Research again* when there is one. Researching shows the waiting dots |
| An **idea page**: the plan, the tools, agents and models, the time it will take | Opened by clicking an idea. What you wrote; the plan (version, summary, tasks, an open question); **What it will take**: size, time, tools, models, agents, where it asks you, branch |
| **Comments** with which Archeus corrects the plan | A thread under the plan. A comment revises the plan to a new version, and Archeus says what changed |

**Where the page is real, and where it is DR-10.** Research is designed as *Core's own planner run on an
idea*, so the page shows the fields the planner already produces for a mission's plan (`Task`: kind,
`min_model_tier`, `workspace_mode`, `estimate` 1–5, `action_classes`, `capabilities_required`). The size is
`planning.validate.cost_band` (D9) applied to those tasks. Running the planner on an idea, keeping its
result, and comments that revise it do not exist, so every research fact on the page is marked **sample**
(`data-k="sample"`, with its source field and DR-10 named; `?prov=1` outlines them) and carries the
"research · requires DR-10" tag. Two rows are real derivations, not samples:

- **Agents:** "picked per task when it starts". The harness, account and model are chosen by the router at
  dispatch (`RouteDecision`), never at planning time. So a page about an idea cannot honestly name the agent
  or the model, only the minimum model tier.
- **Time:** "not estimated". Core sizes work in bands and never in hours (domain-model §7.2: "bands, never
  precise"). The owner asked for an estimated time; showing one would contradict a deliberate rule of the
  architecture, so it is not invented here. **Q11** asks whether to change that rule.

**Results:** E has 42 captures (21 states, desktop and phone), and all pass. D is byte-identical (33 of 33).

**Question added.**
- **Q11.** The idea page cannot show a duration, because Core deliberately estimates size in bands
  (low/medium/high), never in time. Keep that rule and show the band (as built)? Or add a duration
  derived from history, for example the median time of past missions of the same band in the same project?
  That would need its own contract and a stated rule.

## 19. Decision register: every owner decision for the V2 UI

**2026-10-06: the owner accepted Direction E as built** ("i am happy with the current E"). LV2-X.1 is
**closed**: E is the chosen V2 direction. This register collects every owner decision for the V2 UI in one
place. Each entry names where it was made. Nothing earlier was edited; where a later decision changes an
earlier one, the change is recorded here.

### 19.1 Process and scope

| # | Decision | Made in |
|---|---|---|
| P-1 | LV2-1 is closed. W2 (human tests H-1/H-2/H-3) was **intentionally skipped**; the decisions stand on automated evidence | LV2-1 gate §6.1 |
| P-2 | **LV2-2 is not authorised.** A design/evidence phase, LV2-X (product UX / IA reassessment), comes first. Completed phases are not renumbered or rewritten | LV2-X brief |
| P-3 | Optimise for a new user understanding and trusting the system, while it stays minimal, calm and sophisticated, not for passing the prototype's own measurements | LV2-X brief |
| P-4 | **No large human-test programme.** The P1 trial is informational only | LV2-X brief |
| P-5 | The data-contract gates DR-1/2/3/4/8 stay as drafted. Missing data is shown as "requires DR-x", never invented | LV2-X brief |
| P-6 | The minimum V1 defects V2 depends on (V-1…V-4, §13) stay in **V1's** gate. V1/P20 is not changed by V2 work | LV2-X brief |
| P-7 | The e-stop's **safety semantics do not change without a new gate**. Only wording and presentation are V2's | LV2-X brief |
| P-8 | No production implementation and no commits during design. Existing evidence, decisions, gates and results stay intact | LV2-X brief |

### 19.2 Decisions from LV2-1, and how E relates to them

| # | Decision (2026-10-05, APPROVED) | With E (2026-10-06) |
|---|---|---|
| LD-2 | Three places (Now · Needs you · Missions) and the phone IA as the V2 direction | **Superseded** by E's five places (19.3, S-1). The phone keeps bottom tabs |
| LD-3 | Fold the Now rebuild, the approval screen, plain-language labels and visible verification into V2 | **Kept.** E's overview, approval component, state words and checks are these |
| LD-5 | Phone approvals are a full page, not a bottom sheet | **Kept.** The approval is on the mission's own page, with its answers in a fixed bar |
| LD-7 | Two-press e-stop: first press primes, second stops, no dialog | **Kept, semantics unchanged.** E never shows the word "armed" (§8 SS rules) |
| LD-9 | "The honest record" voice: every clause traceable to a recorded field | **Kept**, and sharpened by S-20 (fewer words, no button captions). Every fact is still sourced, and gaps are tagged |
| D-1 | Rows carry project · branch; remote, operation and environment stay hidden until DR-2/6/4 | **Kept** |
| D-2 | V1's naming retained | **Superseded for place names** by S-1 |
| D-5 | LE8 presentation as the target, with a one-row decision bar, 20 px list headers, and §F typography as the default | **E's presentation is now the target.** The one-row decision bar (S-9) and §F typography survive. LE8's typography stays an untested variant |

### 19.3 The V2 UI as decided (Direction E)

**Structure**

| # | Decision | Review |
|---|---|---|
| S-1 | Places: **Overview · Missions · Ideas · Projects · Control**, the same on desktop and phone | §18.1 |
| S-2 | Desktop: a system bar (safety state in words, Core connected, Tell, e-stop) and a left bar with the places, then **the projects, always visible**. The open project is selected; the project of the open mission is only marked | §17.1, §18.1 |
| S-3 | The **mission lines** (dots and dashes) live on the Missions page only, not in the left bar | §18.1 (changes §17.1) |
| S-4 | Phone: bottom tabs for the five places. A mission, a project and an idea are each their own page, with a back button and **no tab bar** | §17.1, §18.1 |

**Overview**

| # | Decision | Review |
|---|---|---|
| S-5 | Desktop order: **Waiting for you** (each with a *Review* button) first, then **errors**, then **Running now**, then Today | §17.1 |
| S-6 | Phone: B's three counters (Waiting · Running · Blocked or failed), then A's Waiting-for-you cards, then errors, running, and the projects | §17.1 |
| S-7 | **Idle:** *Tell Archeus what to do* first and bright (B's button), then **what was done today and the projects**. Fewer words, not an empty page | §17.1, §18.1 (changes §17.1) |

**The mission page**

| # | Decision | Review |
|---|---|---|
| S-8 | **One page per mission on which every state happens.** At the top: back, title, state, project, branch. Under them, **the mission line**: B's connected dots for the six phases, completed phases as **green ticks**, a failed phase as a **red cross**. Then the plan's steps (green ticks), right now, context, and a **terminal-style activity log** | §17.1 |
| S-9 | **A decision appears as a component under the line**, pushing the page down: what you approve, why Archeus asks, what changed. Desktop: **Approve filled on top**, Ask for changes and Reject outlined below. Phone: the answers are **fixed at the bottom of the screen**: **Reject** left, **Changes** centre, **Approve** right | §17.1, §18.1 |
| S-10 | **After Approve**, the component disappears and the line shows **"Approved ✓"**. Clicking it opens the decision record: what was approved, when, and every earlier answer and instruction | §17.1 |
| S-11 | **An error turns the page red** with the failed phase crossed. A component under the line gives why, plus **Explain the error · Ask Archeus to fix it · Cancel mission**. The log below shows what went wrong | §17.1 |
| S-12 | **Explain the error** asks the agent that ran the mission. It shows a loading state, then the answer written as it arrives | §17.1 |
| S-13 | **Ask Archeus to fix it** takes your instructions, then runs the mission again | §17.1 |

**Safety**

| # | Decision | Review |
|---|---|---|
| S-14 | E-stop pressed once, desktop: **red across the whole window** (A) | §17.1 |
| S-15 | E-stop pressed once, phone: B's red banner | §17.1 |
| S-16 | Emergency stop engaged: A's stopped frame, with *Resume work…* (PIN) | §17.1 |

**Projects and Ideas**

| # | Decision | Review |
|---|---|---|
| S-17 | **Project page:** the **timeboard** (B's phase columns, each of the project's missions where it stands), then done today, activity, the project's ideas, and every detail about the project | §18.1 |
| S-18 | **Ideas:** a big central button for an idea for a **new project**, and beside it one that records the idea and **starts it**. Below, every project with its own *+ Idea*. Each idea can be **changed or started**, and starting one creates a mission | §18.1 |
| S-19 | **New idea is a popup in the middle of the screen** on desktop and phone. On the phone, an idea's *Change / Start* are **small buttons at the side** of its row | §18.6 |
| S-20 | **The idea page**, opened by clicking an idea: what you wrote, a **Research** button (Archeus works out the idea and how to build it), the **plan**, **what it will take** (size, time, tools, models, agents, where it asks you, branch), and **comments** with which Archeus revises the plan | §18.6 |

**A rule for the whole product**

| # | Decision | Review |
|---|---|---|
| S-21 | **No caption text under buttons, anywhere.** A button says what it does; its consequence is its tooltip. A fact about the decision, such as the expiry, stays | §18.1 |

### 19.4 Questions settled by accepting E as built

These were open, and E answers them as built. Each one stays open to change at the owner's word.

| Q | Answer as built |
|---|---|
| Q1 Direction | **E** |
| Q2 Place names | Overview · Missions · Ideas · Projects · Control |
| Q4 / Q8 Record as a place | No. The record is each mission's activity log and its decision record, so **DR-7 is not needed** |
| Q5 Tell's prominence | In the system bar always; the lead of the page when idle |
| Q7 Error actions, desktop | In the component under the line, the same place as a decision (matches the phone) |

### 19.5 Still open

| Q | Question |
|---|---|
| Q3 | "Armed" in V1: change P20's copy and Core's recorded reason (V-4), or keep the word off V2 only? |
| Q6 | The LV2-2 plan's Q1–Q6, including whether the V2-U0 human gates (PR-5, PR-3, later PR-1, PR-6) stay as recorded |
| Q9 | **DR-9** (a message to a mission's agent, behind Explain and Fix): draft the gate now, or ship Fix as "run again" with the note recorded and hold Explain back? |
| Q10 | **DR-10** (ideas: direct capture, research, editing, comments): draft now, or ship Ideas as list + start + capture through Tell first? |
| Q11 | Time on the idea page: keep Core's size bands (as built), or add a duration derived from history under its own contract? |
| — | **Motion** for E (the thread travelling along the mission line on a phase change) is not yet prototyped or decided |

### 19.6 Roadmap from here

- **LV2-X.1: closed** (E).
- **LV2-X.2** refines E:
  - the states not yet drawn: loading, Core unreachable, light theme, forced colours, 200 % text, reduced motion;
  - motion;
  - the stress corpus (twenty open missions, many ideas);
  - **Qt = Chromium** on every layout fact;
  - a replay of real V1 Core data, to prove every fact is known or derived;
  - drafts of DR-9 and DR-10 if Q9/Q10 say so.
- **LV2-2** is then re-planned on E and **still needs the owner's authorisation**.
- P26 still comes before any V2 production work.

---

## A. The prototype

### A.1 Running it

`py prototypes/v2-later/tools/lvx_shots.py [a b c]` serves the lab on loopback, shoots every
direction × state × device into `results/lvx/`, and writes the check. In a browser, use
`lvx/index.html?d=a|b|c&v=home|live|decide|mission&s=normal|idle|primed|stopped&id=<mission>`.
`&prov=1` outlines every fact by its kind. In the live page the e-stop works: press once to prime
it (it lapses after 3 s), and press again to stop.

Files:

| File | Content |
|---|---|
| `lvx/data.js` | The shared model over the LV2-0 fixture: `K()`/`NR()`, the explanation frame, the decision fields, the scenarios, the phases |
| `lvx/base.css`, `lvx/shell.js` | Tokens, §F roles, the shared e-stop component |
| `lvx/{a,b,c}.{js,css}` | The three directions |

### A.2 The automated check (a floor, not the judgement)

For every capture the check fails on any of the following:

- a page error;
- the word "armed";
- a fact without a source or kind;
- fewer than six facts (a screen that renders nothing must not pass);
- sideways overflow;
- any of the fixture's unrecorded facts (remote URLs, "deploys to staging", "changes 14 files",
  "Into main", the proposed operation);
- a phone target under 44 px.

**Result: 42 of 42 captures pass** (`results/lvx/check_abc.txt`). Each screen renders 15–92 sourced
facts. The check was **mutation-verified**, five of its six clauses at least: a planted "armed", a
planted "deploys to staging", an unsourced fact and a 3,000 px element each failed every screen
they were planted on, and a direction that renders nothing failed the fact floor. The phone
target clause was not planted. After the plants were removed, every screen passed again.

**What the check cannot say:** whether a screen is good, whether a newcomer understands it, or
whether any of it is trusted. That is §10, and it is judgement.

Corrections made during review (prototype only):

- The stopped scenario now reads every clock at the moment of the stop, so expiries agree.
- The idle day's record now ends with the accepted review.
- A's Today zone no longer labels day totals "since you looked".
- A's *Ask Archeus to fix it* now states only what the state machine does: unblock, then run
  again. Whether an unblock carries a note is one more thing to verify against Core (§8.2).
