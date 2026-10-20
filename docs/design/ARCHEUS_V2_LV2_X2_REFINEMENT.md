# Archeus V2 — LV2-X.2: Direction E refined as one product

**Status: PROPOSED (2026-10-06) · design only · awaiting the owner's review.**
**Update: LV2-X.3 corrects this package against Core and a real-data replay — see
[ARCHEUS_V2_LV2_X3_CORRECTION.md](ARCHEUS_V2_LV2_X3_CORRECTION.md). This document's captures are archived in `results/lvx/x2/`.**
No production code, V1 or P20 file is changed. Nothing is committed. E stays the accepted direction
(reassessment §19); this package refines it and proposes; it decides nothing the owner has not decided.
E as accepted (`?d=e`) and D are untouched: all 85 of their captures are byte-identical after this work.

Prototype: `prototypes/v2-later/lvx/` with `?d=e2` (`e2.js`, `e2.css`, `e2fx.js`).
Review page: `prototypes/v2-later/lvx/gallery.html` (opens on the refined E; switches to E as accepted, D, A·B·C).
Captures and checks: `prototypes/v2-later/results/lvx/` (`e2_*`, `check_e2.txt`, `motion/`, `qt/`, `mutate_e2.txt`).

---

## 0. The answer first

**What was done.** E is drawn as one coherent product: 66 states × desktop and phone (132 captures, plus 12
full-page phone captures), covering every overview state, every mission state, the approval, the error,
the stop and resume flows, Tell, projects, ideas, Control, a stress day, three journey hand-offs and the light
theme. The light along the mission line is prototyped, measured and specified. The same screens were loaded in
the shipped desktop shell (QtWebEngine 6.11, Chromium 140) and compared with Chrome.

**What the refinement changed, in one paragraph.** The desktop overview now shows *what needs you* (left) and
*what Archeus is doing* (right) above the fold even on a busy day, without changing E's order. Every ended state
has an outcome. The approval says what happens if you approve, as content rather than a button caption. The error
separates what Archeus knows from what it does not. Projects have an identity (a monogram in one of six shapes;
colour stays for state). The phone keeps running work visible on every root place. Core-unreachable, loading,
first run, rejection, cancellation, expiry and resume are designed rather than left blank.

**Three things found in Core that the accepted E got wrong or cannot do yet** (§2). None changes a safety
semantic; each is presented honestly in the prototype and needs the owner:
1. E's copy said *resuming needs your PIN* on every surface. P20 D10 approves a PIN step-up only for a
   **paired** device, and it is not built (blocked on P20 V2-3). The refined copy makes no PIN claim on the
   local desktop, and shows D10's step-up on the phone, tagged *not built*.
2. E's stop copy said *new work is refused*. A mission started while stopped is created and then **blocked**
   (P20 gate item 5). The copy now says *nothing runs until you resume*.
3. Three of E's buttons have **no HTTP route in Core**: *Cancel mission*, *Ask Archeus to fix it* on a
   **failed** mission (re-plan), and *Start* on an idea (promote happens only inside the conversation). And
   the fix note on a blocked mission is not even recorded, because the resume route takes no note.

**Does it meet the product goal?** Closer, not demonstrably. §16 answers the seven questions one by one. Two
remain weak on purpose-built evidence: *what happens if I act* is visible for the approval but only as a hover
tooltip for every other button, which a phone cannot show (a direct tension with S-21); and nothing on a busy
screen says, in words, that Archeus coordinates *agents*. No person has seen these screens.

---

## 1. Scope, and what stayed fixed

| Kept exactly | Where it is honoured |
|---|---|
| E's five places, desktop frame and phone tabs; drill-downs as pages with Back and no tabs | every screen |
| LD-3, LD-5 (phone approval is a full page), LD-7 (two presses, no dialog, never "armed"), LD-9, D-1 (project + branch; no remote, operation or environment) | §5, §6, the gate |
| The one-row decision bar; §F typography | phone answer bar; every heading |
| Q4/Q8: no Record place; Q5: Tell always in the top bar, the lead when idle; Q7: error actions under the line | §4, §6 |
| P20's safety semantics: Core-down authority, re-arm, authentication, *no new work until re-armed*, confirmation, accidental-activation protection, D10, stream and shell-credential boundaries | §2.2; only words and layout changed |
| DR-1/2/3/4/8 as drafts; DR-9, DR-10 as named gaps | gap tags on screen; no new contract |

Open and still open: Q3, Q6, Q9, Q10, Q11, and motion (§10 is a proposal). Q10 is shown both ways (§7.2)
and not chosen.

---

## 2. What Core actually does, and where E disagreed

Read from the code for this phase (file references are to `archeus/`).

### 2.1 Facts the refinement is built on

| Area | Fact | Source |
|---|---|---|
| Cancel | `cancel` exists (CREATED, PLANNING, BLOCKED, PAUSED, FAILED → CANCELLED; not from EXECUTING). **No HTTP route**; reached only through the conversation's cancel verb | `core/application/commands.py:486-495`, `api/routes.py` |
| Reject | three records: `approval.state_changed` (reject), `plan.state_changed` (rejected), `mission.state_changed` APPROVAL_REQUIRED → CANCELLED, reason `plan vN rejected` | `authorization.py:659-681` |
| Expiry | `approval.state_changed` (`ttl_elapsed`). **The mission does not move**: the mission machine has no expiry edge. Plan TTL is 24 h, action 2 h | `authorization.py:42-43, 808-819` |
| Review | accept → COMPLETED; changes → REPLANNING; a reject leaves the mission where it is | `verification.py:495-534` |
| Fix | a blocked mission: `POST /v1/missions/{id}/resume` (unblock → redispatch), **no note in the body**. A failed mission: `replan` exists, **no route** | `routes.py:168-170`, `commands.py:462-484` |
| Ideas | only `GET /v1/ideas`; start (promote) happens inside the conversation | `routes.py:1104`, `conversation.py:470` |
| Plans | every version kept (`supersedes_plan_id`); no diff endpoint, a v1 → v2 difference is computed client-side | `work.py:171-213` |
| Stop, Core down | only `archeus estop` and the tray's Emergency stop; the page holds no local authority | P20 gate items 1, 15 |
| While stopped | the policy denies every action; **Approve** is judged again, refused, and stays PENDING; **Reject and Ask for changes still work**; a mission started now is created, then BLOCKED | `policy/engine.py:123`, `authorization.py:711-720`, gate item 5 |
| Re-arm | `POST /v1/rearm` (control); counts only on Core's answer; missions the stop blocked **stay blocked** until each is resumed | `routes.py:634-638`, `executions.py:418-441`, gate item 18 |
| D10 | PIN step-up on re-arm **from a paired device**, approved, **not built** (P20 V2-3) | P20 gate l.268-272, 937, 1029 |
| Notifications | none in V1 (Notification API, web push, sound); P20 D8 moved them to P21; "a notification never approves" | P20 gate l.334, l.1021 |
| Offline | V1 copy: "Offline — nothing you do here is sent. Work on the computer running Archeus continues."; every command disabled | `clients/app/src/data/connection.ts:83-93` |

### 2.2 Conflicts found, and how they are presented (no semantic change)

| # | E said | Core / P20 says | Refined presentation | Owner |
|---|---|---|---|---|
| C-1 | "Resuming needs your PIN" (all surfaces) | D10: PIN only from a paired device; not built | Desktop: no PIN claim ("Resuming from this computer needs no PIN"). Phone: a PIN page tagged *PIN step-up · not built · P20 V2-3* | V2-3 is P20's; the copy waits for it |
| C-2 | "New work is refused" | new missions are created, then blocked | "Nothing runs until you resume. A mission started meanwhile is blocked." | wording only |
| C-3 | Cancel mission (S-11) | no route | button kept, tagged *cancel · no route in Core* | **Q12** |
| C-4 | Ask Archeus to fix it, on FAILED | `replan` has no route | tagged *fix · no route in Core* | **Q13** |
| C-5 | Fix "with your instructions" | the resume route takes no note | tagged *instructions · DR-9* (it was DR-9 already; now also *not recorded*) | Q9 |
| C-6 | Start (an idea) | promote only inside the conversation | tooltip names it; listed under Q10 | Q10 |
| C-7 | "If nobody decides, it expires and nothing runs" | true; and then nothing is defined | an *Approval expired* outcome tagged *what happens next · Core: no expiry edge* | **Q14** |

The gate now fails any capture that says "New work is refused", or that claims a PIN on the desktop (§13).

---

## 3. Screen and state inventory

Every row is captured on desktop (1,440 × 900) and phone (390 × 844, DPR 2) as
`results/lvx/e2_{desk,phone}_<state>.png`, and reachable as `lvx/index.html?d=e2&<query>`.

| Place | States | Query |
|---|---|---|
| **Overview** | busy (`home`), stress day (`home_x2`), quiet (`idle`), no missions yet (`empty`), first run (`noprojects`), loading, Core unreachable (`offline`), stop primed, stopped, resuming, resumed | `v=home` + `s=idle\|empty\|noprojects\|loading\|offline\|primed\|stopped\|resumed`, `resume=sending`, `corpus=x2` |
| **Tell** | dialog, reading, the work it made | `tell=1\|sent\|done` |
| **Missions** | all, stress day, one project | `v=missions`, `f=<project>` |
| **Mission** | running, verifying, planning, approval, approve sent, approved, decision record, result review, accepted, rejected (earlier), just rejected, blocked, explain (asking, answer), fix, failed, cancelled, done, approval expired, stopped, approval while stopped, still blocked after a stop, Core unreachable, loading, long title, opened from a notification | `v=mission&id=…` + `did=approve\|reject\|accept\|expire`, `sending=approve`, `drawer=approval`, `ask=explain\|fix`, `from=notif` |
| **Projects** | list, stress day, project page, project page on the stress day | `v=projects`, `v=project&pid=…` |
| **Ideas** | landing, stress day, current Core only (Q10), new idea, idea page, plan revision, not researched, researching | `v=ideas`, `core=1`, `compose=…`, `v=idea&iid=…`, `rev=1`, `research=1` |
| **Control** | normal, stopped, Core unreachable | `v=control` |
| **Resume** | phone PIN page | `v=resume&s=stopped` |
| **Journeys** | project from a mission, mission from a project, idea from a project with its revised plan | `from=mission:…`, `from=project:…` |
| **Light theme** | overview, approval, error, stopped | `theme=light` |

Data status of every new element is in §2 and in the captures themselves: each fact carries `data-k`
(known, derived, not recorded, sample) and `data-src`; `?prov=1` outlines them.

---

## 4. Desktop, refined

| Element | E as accepted | Refined | Why |
|---|---|---|---|
| Top bar | safety, Tell, Stop | adds **"N running"** (a link to Missions#running) | "what is Archeus doing" from any page |
| Left bar | places, projects | each project: **monogram**, name, **one state dot** (its most urgent: amber waits, red problem, blue running), open count | which project is busy, without opening it |
| Overview | one column: waiting, problems, running; Today on the right | **two columns, one reading order**: left *what needs you* (Waiting for you, then Blocked or failed), right *what Archeus is doing* (Running now, then Today). Caps: waiting 3 when something is blocked, else 5; problems 3; running 4; "N more" goes to Missions | at 1,440 × 900, E put Running below the fold whenever three decisions waited (§9) |
| Decision row | 4 lines | 3 lines: kind and expiry; title; *where · why* on one line | six waiting decisions fit with the problems still above the fold |
| Zone names | "Needs attention" | **"Blocked or failed"** | the same words as the phone counters and the state chips; "stopped" stays the e-stop's |
| Mission page | head, line, component, two columns | head (the project is a link), line, the component or an outcome, then **left**: Right now, Plan, Activity; **right**: Verified, Your decisions, Context | "what was verified" and "what did I approve" are visible without opening anything |
| Activity | the full log | the **last 8 lines**, "Show all N lines" | the log stays subordinate to the explanation |
| Dialogs | idea composer centred | Tell uses the same centred dialog | one dialog form |
| Shell | — | `color-scheme` set, a stable thin scrollbar gutter | the desktop shell draws classic scrollbars (§11) |

## 5. Phone, refined

| Concern | Decision in the prototype | Status |
|---|---|---|
| Navigation | 5 tabs (icon over label, 60 px + safe area, badge on Missions); a pushed page has **Back + the parent's name** and no tabs | E (S-4); the named back label is new |
| Running-work visibility | on root places a **live strip docked above the tabs**: "6 running · Fix the flaky date test · step 4 of 7 ›" (one mission: opens it; several: Missions#running) | **proposed** (PX-3) |
| Title hierarchy | root: the place as a large title (Overview's is its statement); pushed: the object's title as the headline | proposed |
| Thumb reach | primary answers in the bottom bar; Stop top-right, deliberate | E |
| Approval controls | fixed bar: expiry, then **Reject · Changes · Approve** (52 px) | E (S-9); expiry moved into the bar |
| E-stop | in the app bar on every page; primed band under it; stopped: the bar becomes the band | E |
| Touch targets | every target ≥ 44 px (wide ones ≥ 32 px tall); inline links are padded to 44 px | the gate enforces it; it found 21 that were not (§13) |
| Long names | titles clamp to 2 lines in lists; full on the page; branches wrap; project names ellipsise beside their monogram | §9 |
| Lists at scale | overview sections show 3 then "N more"; ideas 3 per project; Missions has scrolling project chips | proposed |
| Offline | the snapshot dimmed; a band with V1's offline sentence and where the stop is; Tell and Stop disabled | PX-11 |
| Back | system Back pops one level; a notification opens the mission with the Overview beneath | §8 |

## 6. Mission, approval and error

**The line** keeps E's six phases, green ticks and red cross, and adds the ends E had no picture for: a
**square** where the emergency stop interrupted the run (red while stopped, still drawn after resume), a
**grey bar** where a mission ended without finishing (rejected at Approve, cancelled at Verify, approval
expired), and **dashed segments** for phases that will never happen. The current node is a ring, not a glow
(PR-5's third term: state figures carry no light).

**The approval component** (PX-5) answers the brief's list on the page itself:

| Asked | Where |
|---|---|
| why Archeus is asking | *Why Archeus asks*: the rule in words; the rule strings behind a disclosure |
| what changed | *What changed since v1*: from the two kept plan versions and your earlier note |
| what will happen | *If you approve*: the first task now, then the rest (from `states.py` and the plan), and what expiry does |
| which project and branch | *Where*: monogram, project, branch, commit, repository (by DR-3's rule), runs on |
| what was verified | *Verified*: "Nothing has run yet, so nothing is verified" for a plan; the named checks for a result |
| when it expires | the component head (desktop) and the fixed bar (phone) |
| what is not recorded | *Archeus does not know*: environment (DR-4), remote (DR-2) |

Pressing an answer shows a **sending** state ("Approving…", the others disabled, "Nothing is shown as
approved until Core records it"). Core's answer replaces the component with one line — "Approved at 15:12.
Archeus started “Build the site” at 15:12." — and the line shows *Approved 15:12 ✓*, which opens the decision
record. While stopped, Approve is disabled with its reason and the other two answers stay live (§2.1).

**The error component** (PX-7): the *because* chain (two hops, as recorded), then three blocks — **Archeus
knows** (checks with exit codes, last checkpoint, steps finished), **Archeus does not know** (why the check
failed: its output is kept by Core, DR-8) and **Asked of you** (Archeus waits: explain, fix or cancel). Red is
held to the rule, the label, the crossed node and the failed check; the body stays in normal ink.

**Ended states** (PX-8) get a neutral *Outcome* in the component's place: rejected ("You rejected plan v1 at
13:40. The mission was cancelled; nothing ran." with *What you rejected*), cancelled (when, how — through a
message, as Core records it — and how far it got), done, approval expired.

## 7. Projects, Ideas, Control

### 7.1 Projects
The list is a grid of project cards: monogram, name, repositories, state chips, and the one mission that most
needs looking at ("Waiting: Upgrade the auth library"). The project page opens with its identity (a large
monogram), then **Now** (the timeboard: empty phases take half a column, three tokens per phase, each token with
its branch), then Done today and Activity beside Ideas and Details. A first-run page explains the six phases and
offers *Add a project…*, which is `POST /v1/projects`, an **admin** route: a device without admin scope gets it
disabled, so no authority moves to the browser.

### 7.2 Ideas
As E, with scale rules (three per project, then "N more") and two additions: a **plan revision** view (v1
struck through beside v2, the changed task marked, the comment that caused it) and a **current-Core** variant
(`core=1`) that shows what Ideas is with no DR-10: the list, *Start* (through the conversation) and "Tell
Archeus an idea"; no composer, research, editing or comments. Both are drawn so Q10's trade-off can be seen;
neither is chosen.

### 7.3 Control
V1's Control sections regrouped by what you come to do, with **Safety first** (PX-17): the state, the stop or
resume button, and five facts about the stop in plain words (what a stop does; nothing runs until you resume;
resuming does not restart missions; where the stop is when Core cannot be reached; whether resuming asks for a
PIN on *this* device). Then Autonomy (the profile and what it asks before, from the recorded rules), Agents and
accounts (incl. P20 D6's read-only opt-ins), Automations, Devices, Appearance, About. Nothing gains authority:
every admin action stays admin.

---

## 8. Navigation and journeys

The prototype carries one level of origin (`from=`) so the back label can name it; production uses the history
stack and keeps the whole path.

| # | Journey | Desktop | Phone | What stays visible |
|---|---|---|---|---|
| 1 | Notification → mission → approval → approved → back | the notification is **P21's** (none in V1); the landing is the mission page with Overview beneath; approve → sending → approved line + decision record → back to Overview, where the row has moved from Waiting to Running | same; Back "‹ Overview"; the answer bar | Stop, safety, the running count; a notification never approves (P20 §14.F) |
| 2 | Overview → waiting mission → decision → back | Review → component → answer → confirmation → Back | card → page → bar → Back | the badge count drops by one |
| 3 | Overview → running mission → project → mission → back | tile → mission → its project (head link, or the left bar where it is marked) → a token → mission; Back names the project | same, Back "‹ archeus", then "‹ Fix the flaky date test" | the left bar keeps the project marked |
| 4 | Project → idea → research → revised plan → back | idea row → idea page → Research → researching → plan v2 → "What changed from v1" → Back "‹ invoicing" | same | DR-10 tags on research and comments |
| 5 | Error → explanation → fix → mission | Explain (asking, then the answer as it arrives) → Ask Archeus to fix it (your note) → Send and run again → the running page | same, buttons stacked | DR-9 on the answer and the note |
| 6 | Stop → stopped → resume | press once (red bar and band, lapses) → twice (stopped band, Resume work…) → resuming (only Core's answer counts) → resumed band: "2 missions the stop interrupted stay blocked … Show them" → Missions#stopped → Unblock and run again | Resume → **PIN page** (D10, not built) → resuming → resumed | the stopped band on every page |
| 7 | Tell → new work → mission | the top bar's Tell → dialog → "Archeus is reading it…" → "Archeus made it a mission" with its line → Open the mission | "+" → Tell page → same | the new mission appears in Missions |

Found and fixed on the way: on the phone a mission page had no way to its project (the head is now a link);
back labels said only "Mission" and "Project" (they name the origin now).

---

## 9. Stress test

**Fixture** (`?corpus=x2`, `lvx/e2fx.js`; synthetic, V1 shapes only): 7 projects including two look-alike pairs
(*invoicing* / *invoicing-api*, *website* / *website-legacy*), a 36-character name and a Unicode one
(*café-menü*); 25 missions: 6 waiting (4 plan approvals, 2 result reviews), 6 running or verifying, 2 failed,
1 blocked, 1 **still blocked by an emergency stop cleared at 11:52**, 2 planning, 5 done, 2 cancelled; look-alike
titles (*Upgrade the auth library* in two projects; *Update the currency formatter* twice in one project;
*Fix the flaky date test* in two projects); a 103-character title; a 79-character task branch; a 46-character
default branch; German and Japanese titles; 13 ideas.

| Inspected | Finding | Outcome |
|---|---|---|
| Overview, desktop | E's single column put *Blocked or failed* below the fold whenever three or more decisions waited, and *Running now* off the first screen | two columns + caps; at 25 missions all four zones start above the fold |
| Overview, phone | the first screen holds the counters and one and a half waiting cards; the rest is one scroll per section | caps of 3 + the live strip; acceptable, not tested on a person |
| Missions | 25 rows read well on desktop; the phone page is 3,900 px long | project chips; proposal: collapse *Done* and *Cancelled* by default on the phone (X.3) |
| Look-alike titles, different projects | told apart by monogram (IN vs IA) and name | holds |
| Look-alike titles, **same** project | told apart **only by branch** (`archeus/x-04` vs `archeus/x-05`), an opaque id; the objectives differ but rows do not show them | **Q15** |
| Timeboard | the two look-alike missions were identical tokens | tokens now carry their branch |
| Long names | titles clamp/ellipsise in lists, wrap on pages; the 36-character project ellipsises in the left bar with its monogram | holds |
| Unicode | Japanese falls back to the system UI font; monogram of *café-menü* is CM | holds |
| Project dots | with 7 projects, 6 dots are amber: when everything waits, the dot stops discriminating | noted in §12 |
| Phone projects | a card overflowed sideways by 310 px (a class collision) — and **the gate had not seen it** (§13) | fixed; the gate fixed |

## 10. Motion — proposal

Prototyped in `e2.js` (`travel`, `progressRow`), measured by `tools/lvx_motion.py`, filmstrip
`results/lvx/motion/filmstrip.png`.

| Question | Proposal |
|---|---|
| When it appears | only when Core records a **phase change** of a mission on screen (here: Approve → Run after you approve). Never for a refresh, a navigation or a running mission |
| What it means | "this mission moved forward, here" — V-1, light is evidence |
| Focus surface (the mission page) | a short head (≤ 22 × 6 px, thread ink, ≤ 0.9 opacity) travels the segment in **600 ms linear** while the segment fills behind it; a ring lands on the node, **0.6 → 1 scale and fades in 240 ms**; the node's core lights at 840 ms. The node's ring state is drawn from the first frame, so the state never depends on the motion |
| Peripheral lines (rows, tiles, timeboard) | no head: the segment fills in **160 ms** (V2's *progress* class); F-6, the edge of vision gets the quietest motion |
| Continuous? | **No.** A running mission does not pulse; the caret in the log does not blink; at rest there are zero animations |
| Interruption | one travel at a time; a second change, or any input, renders the end state at once (F-5) |
| Safety | the light never runs while the stop is engaged, and engaging the stop ends any travel; the stop's own 2-s lapse bar (transform only) is the only motion in the safety frame |
| Reduced motion | the end state at once; the error explanation appears whole |
| Other useful motion | the primed stop's lapse bar; the explanation arriving as the agent writes it; the waiting dots, only while something is actually awaited. Nothing else |

**Measured (Chromium 149):** only `transform` and `opacity` animate; four animations, the longest 840 ms; nothing
runs 1.15 s later; no animation with the stop engaged; the row fill is one 160 ms transform; zero animations at
rest on the overview, a running mission, the stress Missions page and the quiet overview; under reduced motion
the Run node is already lit and nothing animates. **In the desktop shell (Qt 6.11 / Chromium 140)** the travel
runs and all four animations are finished at 900 ms. One defect was caught by the filmstrip, not the checks: an
easing given to the whole ring animation warped its timeline and the ring landed while the head was still
travelling; the easing now belongs to the landing segment only.

**Still open for the owner:** whether the head is wanted at all (the fill and the landing ring alone also read
as progress), and F-1's demotion rule when many missions change at once.

## 11. Desktop and browser consistency

`tools/lvx_qt.py` loads 21 screens in a real `QWebEngineView` window (as `archeus gui` does) and in Playwright's
Chromium at 1,440 × 900, reads element boxes, counts, page size and feature support from both, and captures the
composed Qt window (`results/lvx/qt/`).

| Run | Result | What it meant |
|---|---|---|
| 1 | 14 of 21 screens differ by exactly 15 px in width | the desktop shell draws a **classic scrollbar** (light grey on the dark page) wherever the main area scrolls; headless Chromium hides scrollbars, so every capture so far has shown a layout the desktop app never draws. Pages that do not scroll matched within 2 px |
| 2 | design fixed: `color-scheme` (dark/light), a **stable scrollbar gutter** on the main area, thin scrollbars; Chromium now launched with its scrollbars | widths agree within 2 px on every screen; heights drift by 3–10 px on long pages |
| 3 | same at the shell's own device pixel ratio (1.5) | no change: the drift is not DPR. It is text metrics between two Chromium builds (149 vs 140), under 1.5 % of position |
| 4 | the check now holds x and width to 2 px and allows y/height 1.5 % | **21 of 21 pass**; the travel runs in Qt and finishes |

**Features used and present in both:** `color-mix()`, `:has()`, `:is()`, `-webkit-line-clamp`, Web Animations
and `getAnimations()`, SVG text (the monograms), and the three §F fonts (Segoe UI Variable Display/Text,
Cascadia Mono). Nothing in the design depends on a browser-only behaviour. **Not checked:** the shell at other
window sizes, high contrast in the shell, and the shell's own frame and tray (outside the page).

## 12. Visual-design critique

Design review, not measurement. Where E (refined) still falls short:

**Too minimal**
- **Nothing says what Archeus is while it is busy.** The first run explains the six phases; a busy overview never
  says that agents do the work. A newcomer sees missions and approvals, not *who* runs them.
- **What Archeus decided is thin.** Approvals are explained; route choices (which agent, which account, why) are
  only in Control. The reset proposal's per-mission decision journal is not in E.
- **Phone consequences.** Apart from the approval, a button's consequence is a hover tooltip (S-21). A phone
  has no hover, so *Explain*, *Fix* and *Cancel* do not say what they do there.

**Too dense**
- The desktop approval is six labelled blocks and a gaps line (~420 px). It earns its height on the first
  decision of a kind; the twentieth deploy approval reads the same.
- The phone approval page is about four screens; the fixed bar keeps the answer reachable, but *Why* and
  *What changed* sit below the first scroll.

**Ambiguous**
- *Review* is the overview's button for every decision and also the name of the last phase.
- A mission blocked by a cleared stop is listed under *Stopped by the emergency stop* while its chip says
  *Blocked*. Both are true; together they read as a contradiction.
- The project dot summarises a project as one colour; on a busy day nearly every dot is amber.
- Look-alike missions inside one project differ only by an opaque branch id (Q15).
- Monogram shapes (circle, square, hexagon, shield, octagon, cut tab) are hard to tell apart at 20 px; the
  letters do the work. Untested by any person.

**Dashboard-like**
- Four bordered zones with counts in their headers is a dashboard pattern. It is the right one for a control
  surface, but the Today stat tiles (Done · Checks passed · Checks failed) are the least actionable thing on
  the overview and the most dashboard-like.
- Nested borders (zone › row › line card) everywhere; a flatter row treatment inside zones would calm it.

**Colour and urgency**
- Amber carries waiting, decision kinds, expiries, badges and project dots at once; on a busy day it is the
  dominant hue.
- The fixture's 8-minute deadline makes *Next deadline* look urgent; Core's plan approvals live 24 h (action
  approvals 2 h). Shown as built, the amber deadline will rarely mean anything. Proposal: show it only within a
  stated window (X.3).

**What works**
- One statement, then zones; state always a word; the explanation frame on the page; gaps named once.
- Red confined to rules, labels and crossed nodes, so an error screen keeps its hierarchy.
- The light theme follows from the V1 tokens alone.

## 13. Automated evidence (a floor, not the judgement)

| Gate | Result |
|---|---|
| Capture gate (`check_e2.txt`): page errors; "armed"; unsourced facts; the fact floor (lowered only for loading, first run, empty, PIN, Tell and resuming pages); sideways overflow; the fixture's unrecorded facts; phone targets < 44 px; **new:** "New work is refused" anywhere, a PIN claim on the desktop, a card narrower than 150 px (240 px on the phone), a looping animation with nothing awaited | **132 of 132 pass**, after it caught 21 small phone targets, a desktop PIN claim inherited from the shared primed hint, a 3-fact phone page, and a 310 px overflow |
| The overflow check itself | **was blind on the phone**: a mobile layout viewport widens to fit wide content, so `scrollWidth − innerWidth` stayed 0. It now measures against the device width. A–E were re-run under it: **0 new failures, all 151 of their captures byte-identical, their check files identical** |
| Mutations (`mutate_e2.txt`) | 8 of 8 planted defects killed (stop copy, desktop PIN, squeezed card, decorative loop, phone overflow, a layout property in the light, light while stopped, light under reduced motion); restored runs pass |
| Motion (`motion/check.txt`) | 11 of 11 |
| Qt vs Chromium (`qt/check.txt`) | 21 of 21 (§11) |

What none of it can say: whether a screen is understood, whether it is trusted, or whether it is good.

## 14. Decisions

### 14.1 Settled (not reopened here)
E and its five places; LD-3, LD-5, LD-7, LD-9, D-1; the one-row bar; §F typography; no Record place; Tell in the
top bar and leading when idle; desktop error actions under the line; P20's safety semantics; the DR gates as
drafts; S-1 … S-21 as recorded in reassessment §19.

### 14.2 Proposed by this package (the owner accepts, changes or rejects each)

| # | Proposal | § |
|---|---|---|
| PX-1 | Desktop overview: *needs you* left, *Archeus's work* right; E's reading order kept; caps (waiting 3 with problems / 5 without, problems 3, running 4) | 4 |
| PX-2 | The problem zone is named *Blocked or failed* | 4 |
| PX-3 | "N running" in the top bar; a live strip above the phone tabs on root places | 4, 5 |
| PX-4 | Project identity: two-letter monogram in one of six neutral shapes; one state dot per project in the left bar | 4, 7.1 |
| PX-5 | The approval component's seven blocks; expiry in its head (desktop) and the fixed bar (phone), not on the line | 6 |
| PX-6 | *If you approve* is content of the explanation, not a caption — S-21 read as "no consequence printed under a button", not "no consequence anywhere" | 6 |
| PX-7 | The error component: chain · knows · does not know · asked of you | 6 |
| PX-8 | An *Outcome* component for rejected, cancelled, done and expired missions; the line's grey end mark and dashed future | 6 |
| PX-9 | Stop copy: primed "Press again to stop N running missions now. Nothing runs until you resume. Lapses in 2 s"; stopped "… Nothing runs until you resume."; no PIN claim on the desktop; D10's PIN page on the phone (C-1, C-2) | 2.2 |
| PX-10 | While stopped: Approve disabled with its reason; Reject and Changes live | 6 |
| PX-11 | Core unreachable: snapshot dimmed, commands disabled, Stop disabled with V1's pointer to the tray and `archeus estop` | 5 |
| PX-12 | A *sending* state for every answer; Core's recorded result as one confirmation line | 6 |
| PX-13 | Mission page: Verified · Your decisions · Context on the right; the log collapsed to its last lines | 4 |
| PX-14 | Back labels name the origin; the project in a mission's head is a link | 8 |
| PX-15 | Missions: project filter chips; *Stopped by the emergency stop* and *Cancelled today* groups | 3 |
| PX-16 | Timeboard: half-width empty phases, 3 tokens per phase, branch on each token | 7.1, 9 |
| PX-17 | Control: Safety first with the five stop facts, then V1's sections regrouped; no new authority | 7.3 |
| PX-18 | Motion as §10 (focus travel 600 + 240 ms; periphery 160 ms; never continuous; never with the stop) | 10 |
| PX-19 | Desktop shell: `color-scheme`, stable thin scrollbar gutter | 11 |
| PX-20 | Tell: dialog → reading → the work it made, with a link | 8 |
| PX-21 | *Add a project…* on first run, for an admin device only | 7.1 |

### 14.3 Unresolved

| Q | Question | Note |
|---|---|---|
| Q3 | "Armed" in V1: change P20's copy and Core's reason, or keep it off V2 only? | unchanged |
| Q6 | The LV2-2 plan's questions, incl. the V2-U0 human gates | unchanged |
| Q9 | DR-9 (a message to a mission's agent), or ship Fix as "run again"? | now also: the resume route records no note at all (C-5) |
| Q10 | DR-10, or Ideas with current Core only? | both drawn (§7.2) |
| Q11 | Idea time: size bands, or a duration from history? | unchanged |
| **Q12** | *Cancel mission* has no HTTP route. Add a route (a Core contract with its own gate), send it through the conversation, or hold the button? | C-3 |
| **Q13** | *Ask Archeus to fix it* on a **failed** mission is `replan`, which has no route. Same three options | C-4 |
| **Q14** | After a plan approval expires the mission stays in APPROVAL_REQUIRED with nothing pending. What should happen, and who decides — Core or the design? | C-7 |
| **Q15** | Look-alike missions in one project differ only by branch id. Show the objective on the row (a known field; an addition to D-1's row), or accept it? | §9 |
| **Q16** | Notifications are P21's. Is the designed landing (the mission page, Overview beneath, never approving) the brief for P21? | §8 |
| **Q17** | The phone's live strip (PX-3) adds 44 px of fixed chrome above the tabs. Keep it? | §5 |
| **Q18** | S-21 on the phone: tooltips cannot be seen, so only the approval says what its button does. Accept, or allow one consequence line for destructive answers (Cancel, Reject) on the phone? | §12 |
| — | Motion: the head, or only fill + ring? | §10 |

## 15. LV2-X.3 — is another pass needed?

**Yes, a short one.** The refinement is complete enough to judge, but three things cannot be settled by more
drawing, and two have not been tried at all.

| Step | Content | Exit |
|---|---|---|
| X.3-1 | The owner reviews this package and decides PX-1 … PX-21 and Q12 … Q18 | recorded decisions |
| X.3-2 | Apply them; resolve the §12 items the owner agrees with (identity line when busy, deadline window, Today tiles, flatter rows, the *Review* wording, the cleared-stop grouping) | captures re-shot, gates green |
| X.3-3 | **The owner's phone**, not an emulator: safe areas, thumb reach, the fixed bar, the live strip, 200 % text, the light theme outdoors | the owner's notes (not a study) |
| X.3-4 | A replay of **real V1 Core data** (ADR-0029 captures) through the prototype, to prove every fact is known or derived on data the fixture did not invent | no invented fact |
| X.3-5 | Forced colours and 200 % text on desktop and phone; the shell at 1,280 and 1,920 px | gates green |
| X.3-6 | Only if the owner wants evidence on §0's last question: a five-second look by three people at the overview and one approval, answering *what is this, what does it need from me* | one note per person; not a programme |
| then | Re-plan LV2-2 on the decided E; P26 before any production V2 work | the owner's authorisation |

## 16. Against the original problem

> A new user should open Archeus and immediately understand what Archeus is doing, what needs their attention,
> what it knows, what it is waiting for, and what they can safely do next.

| Question | Verdict (design review) |
|---|---|
| What is Archeus doing? | **Mostly.** Running work is visible on every desktop page (the running pill, the right column) and on the phone's root places (counters, live strip). But nothing says *agents* do it (§12) |
| What does it need from me? | **Yes.** One statement, waiting first, a badge, the next deadline |
| What did it decide, and why? | **Partly.** Approvals explain why; route decisions and the plan's reasoning do not reach the mission page |
| What is running, waiting, blocked, failed? | **Yes.** State is always a word, a colour and a place on the line |
| Which project and work item? | **Yes, with one gap**: look-alikes inside one project (Q15) |
| What happens if I act? | **For the approval, yes. Elsewhere, only on hover** — not on the phone (Q18) |
| What does Archeus know and not know? | **Yes.** Every gap is named once; the error separates the two explicitly |

**So the design is not yet ready to declare done.** It is a coherent, honest product that a returning user can
operate, and it now covers every state Core can put a mission in. It does not yet prove the five-second
question for a *new* user, and it carries five open command gaps (Q12–Q14, plus DR-9 and DR-10) that decide
whether several of its buttons can exist. Nothing here has been seen by anyone but this review.

---

## A. Files

| File | Content |
|---|---|
| `lvx/e2.js`, `lvx/e2.css` | the refined E (one module, one stylesheet, V1 tokens only) |
| `lvx/e2fx.js` | the settled missions, the ideas, `?corpus=x2`, the scenario states (`s=empty\|noprojects\|resumed`, `did=reject\|accept\|cancel\|expire`); no-op unless `d=e2` |
| `lvx/index.html`, `lvx/shell.js` | load the three files; `?theme=` sets the theme. A–E unaffected (verified byte-identical) |
| `lvx/gallery.html` | opens on the refined E |
| `tools/lvx_shots.py e2` | the 132 captures and the gate; `LVX_ONLY=a,b` runs a subset |
| `tools/lvx_motion.py` | the motion checks and filmstrip |
| `tools/lvx_qt.py` | the shell comparison (opens a Qt window) |
| `tools/lvx_mutate_e2.py` | the gate mutations |
