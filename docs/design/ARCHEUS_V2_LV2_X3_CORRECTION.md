# Archeus V2 — LV2-X.3: E corrected against Core

**Status: PROPOSED (2026-10-06).** Design only. No production code, V1, P20, Core or API contract is changed by
this package, nothing is committed, and LV2-2 is not started. It corrects the refined E of
[LV2-X.2](ARCHEUS_V2_LV2_X2_REFINEMENT.md) and decides nothing on the owner's behalf: every "resolution" below
is a proposal unless it only restates what Core already does.

**Update 2026-10-06 (LV2-X.4):** the owner decided Q12–Q18 and the six replay inconsistencies. §9 records the
decisions as the V2 interpretation, the prototype changes that apply them, the dependencies by owner, and the
exit condition still open. Where §0–§8 and §9 differ, §9 holds.

**Update 2026-10-06 (LV2-X.5):** the owner ran the phone pass on a real phone. Two findings (button order, and
a phone layout "too big" twice) were fixed and the owner approved the result (§9.7). One blocker remains: an LV2-2
plan written for E.

---

## 0. The answer first

**Recommendation: NOT READY FOR LV2-2.**

The design now communicates the eight things the brief asks about, on desktop and phone, and it survived a
replay of a real Core's data. That is a real change from X.2. What still stands in the way is not drawing:

1. **Three controls depend on decisions only the owner can take.** Core cancels a mission only through a
   conversation command, cannot retry a failed mission at all, and leaves a mission whose plan approval expired
   stranded and silently dropped from the attention list. The design now represents each truthfully (Cancel…
   through Tell; "retrying is not possible yet"; an expired outcome with Cancel…), but building LV2-2 on top would
   ship those workarounds as the product. Each needs a yes/no: accept the workaround, or open a Core gate.
2. **The safety copy for resuming has one undecided rule** (V2-3: does the desktop ask for a PIN too?). Today
   nothing asks; D10 is approved for paired phones, not built, and held until V2-3 is decided.
3. **Nobody but the author has looked at it**, and the phone has only been seen in emulation. The brief's own test —
   a new user understanding it within seconds — is unproven.

**What would make it READY:** the owner's answers to §2's open rows (Q12 V2-3, the three Q14 items, the Q16 brief to
P21), and one owner pass of the nine phone screens in §6 on a real phone (the LAN tool in §A serves them). No further
design pass is needed for either.

---

## 1. What changed in the prototype

Only corrections the brief asked for, or that the real-data replay forced. `?d=e2` is the corrected E; X.2's 132
captures are kept unchanged in `results/lvx/x2/` and in the gallery as *E refined · LV2-X.2 (archived)*.

| # | Correction | Why |
|---|---|---|
| 1 | Every branch is Core's: `archeus/msn_<ULID>`; a row shows `archeus/…XFPC` (the id's last four), the mission page the whole | Core names the branch after the mission id (`queries.py:35`); X.2 printed `archeus/m-4c1e`, which Core never produces |
| 2 | A look-alike (same title, same project) shows its objective under the title, and when it was asked if that differs | Q15 |
| 3 | The mission head is a sentence with Archeus as its subject: "Archeus is working on this. Claude Code · for 20 min", "Archeus is waiting for you to approve task 2.", "Archeus cannot go on; it waits for you." | §5 of the brief |
| 4 | Running work names the agent and its step: "**Claude Code** is on step 4 of 7: Run the date suite 50 times"; the overview says "Meanwhile Archeus is working on 2 missions"; the zone is "Archeus is working on" | §5; harness and model are on the live item (`live.py:69-77`) |
| 5 | *Waiting for you* counts pending approvals, not mission states: a **step approval** (Core blocks the mission at dispatch) is a decision, drawn as "Run this step?" with Approve / Reject only | `authorization.py:529-535, 644`; X.2 would have filed it under *Blocked or failed* |
| 6 | The error component offers only moves Core has: **Start over** or **Run again** (the resume route; which one depends on `held_from`) and **Cancel…** (the conversation's cancel command, prepared in Tell). *Ask Archeus to fix it* and the note field are gone; *Explain* is drawn only with `dr9=1` | Q14 |
| 7 | A failed mission says "retrying it from here is not possible yet" and offers Cancel… only | Q14 (`FAILED → replan` exists; nothing fires it) |
| 8 | An expired plan approval: "Archeus does not ask again on its own, and this mission stays here until you cancel it", with Cancel… | Q14 |
| 9 | Start… on an idea prepares the request in Tell | Q14 (promotion happens only in the conversation) |
| 10 | Tell while stopped says commands still work and a new request is kept, not read; its answer is "Kept, not read … send it again after you resume" | Q13 |
| 11 | Resuming from the phone asks no PIN (what P20 does today); D10's PIN page is drawn separately as `pin=d10`, labelled approved-not-built; approving a **deploy** from the phone asks for the PIN (built) | Q12 |
| 12 | Action consequences on the action (Q18): state-changing actions in a card are rows "verb / what it does"; the fixed answer bar says the outcome in the label (*Approve & run · Send back · Reject & cancel*) | Q18 |
| 13 | The phone strip is a sentence: "Archeus is working on 2 missions / Fix the flaky date test · step 4 of 7 · +1 more" | Q17 |
| 14 | Notifications: what they say, where a tap lands, and what changed since ("Opened from a notification sent at 14:58 · Since then you approved it, at 15:12") | Q16 |
| 15 | Robustness the replay required: expiries past midnight ("tomorrow 14:05", "in 24 h 0 min"); a queued mission ("waits for an agent to be free"); unknown task states; a null model; no default branch | §4 |

---

## 2. Q12–Q18

| Q | Question | Evidence | Proposed resolution | Status |
|---|---|---|---|---|
| **Q12** | Resume and the PIN | `POST /v1/rearm` takes only an idempotency key and checks only that the caller is a user device (`executions.py:436-441`, `schemas.py:821`). A paired phone holds `control` by default (`auth.py:35`), so **today it resumes with no PIN**, like the desktop. **D10** (p20:268-273, decided p20:336): step-up on re-arm *from a paired device*; not built, **held** until V2-3 (p20:937). **V2-3** (p20:1029): device-specific copy, or widen D10 — the owner's. Step-up for **approvals** is built (`authorization.py:562-570`): a deploy approved from a phone asks for the PIN | Three layers, kept apart. *P20 guarantees today:* no PIN to resume on any device — the copy says so per device ("Resuming from this phone does not ask for a PIN"). *V2 wants eventually:* D10's PIN on the phone — drawn only as `pin=d10`, tagged *approved, not built*. *Undecided:* whether the desktop asks too (V2-3) — no copy claims either way. The phone approval PIN is drawn because it exists | **Open (V2-3)** — copy resolved |
| **Q13** | The stopped state | `POST /v1/missions` does not check the stop: the mission is created and walks to REASONING; with a production brain the planner call is refused and it **stays in REASONING with no edge out**, also after the re-arm (`calls.py:105-107`, `planning.py:129-137`, `states.py`); with the stub brain it is BLOCKED by `builtin:estop` (gate item 5). **Through Tell** — the V2 path — only control verbs work; a request is declined, **no mission is made**, and the reply wrongly says "no harness that can make the call is installed" (`intent.py:133-141`, `conversation.py:346-359`) | Keep "Nothing runs until you resume." Control fact: "Nothing is planned or run until you resume. A request you send meanwhile is kept, not read." Tell while stopped explains it before sending, and its answer reads Core's *reason* (the stop), not its misleading reply text | **Resolved for the design**; two Core defects recorded (§3 M-15, M-16) |
| **Q14a** | Cancel mission | No route (`routes.py:35` lists it as deliberately absent). The conversation command `cancel <mission>` (or `stop`) by id or exact title is deterministic, works while stopped, and cancels CREATED, PLANNING, BLOCKED, PAUSED, FAILED and — by the reject edge — APPROVAL_REQUIRED (`grammar.py:27-31`, `commands.py:486-495`) | **Cancel…** opens Tell with `cancel msn_…` (the id, because a title is ambiguous between look-alikes) and says "the mission ends when Archeus reads it". Not a fake: it is Core's own command, shown before it is sent | **Open**: accept the Tell route, or gate a cancel route |
| **Q14b** | Ask Archeus to fix it | A blocked mission can be resumed (`POST …/resume`, no note); what that does depends on where it was held: from EXECUTING/VERIFYING it runs again on the same plan, otherwise it starts over from UNDERSTANDING (`commands.py:462-484`). A **failed** mission: `replan` exists, no route or verb fires it. A note never reaches an agent (DR-9, undrafted) | Blocked: **Run again** or **Start over**, each saying which. Failed: no button; "retrying it from here is not possible yet". Your instructions: tagged DR-9, not drawn. Explain: only with `dr9=1` | **Open**: retry for FAILED (a route gate or accept), DR-9 (Q9) |
| **Q14c** | Start on an idea | Only `GET /v1/ideas`; promotion is the brain reading a request with the idea as its target, no fixed words (`brain/intent.py:72-74`, `conversation.py:455-488`) | **Start…** prepares "Make the idea “…” a mission." in Tell and says Archeus may ask what you mean | **Open** with Q10 (DR-10 or current Core) |
| **Q14d** | An expired approval | Only the approval moves (`approval.state_changed`, ttl_elapsed). Plan: the mission stays APPROVAL_REQUIRED, the attention list drops it silently, no event tells anyone; ways on are the plan-edit route (not in E) or the cancel command. Task: stays BLOCKED; resume asks again. Action: the execution ends rejected; the mission's end state is unpinned by any test (p11 and the code disagree) | Draw only what is defined: "Nobody decided plan v1 by 15:52. Nothing ran. Archeus does not ask again on its own, and this mission stays here until you cancel it." + Cancel… + *what happens next · undecided* | **Open** (what should follow) |
| **Q15** | Look-alike missions | Core gives title (≤ 120), objective, project_id, `created_at`, the branch from the id. It gives **no start time, no short id, no human branch**. The replay's two look-alikes were created 2 s apart, so "asked 14:05" told them apart **not at all**; their objectives did | Identity = **title · project · branch tail**, always (D-1). A look-alike adds its **objective** under the title (desktop one line, phone up to two) and "asked HH:MM" only when the times differ. Works on Overview, Missions, the timeboard, Tell's result, notifications (project, plus the time when it helps) and the mission page | **Resolved** (proposed) |
| **Q16** | Notifications | P21 owns them (D8); no P21 gate exists. Rulebook §17: OS notification only for an approval and the stop, while the window is hidden; phone push the same two. The API notes add blocked missions and more. A push carries "a title + deep link" only. Rule 18: never approve from a notification | Content rule: *what happened · which mission · which project*; one tap opens the decision with Overview beneath; never an action button. The landing says it came from a notification and **what changed since** (approved, expired, cancelled). Blocked missions drawn dashed, as P21's call | **Open for P21**: blocked missions; whether a mission title may leave the computer in a push |
| **Q17** | The phone's running strip | `q17.txt`: in 14 cases (7 states × 2 pages) it never covers content; it is absent when idle, while stopped (the red bar owns the frame) and when Core is unreachable (a stale "working on" would mislead); waiting and failed missions do not change it — they have the badge and the overview | Keep it, as a sentence with Archeus as subject. It answers only "is Archeus doing something"; it never carries waiting or safety | **Resolved** (proposed) |
| **Q18** | Consequences on the phone | `x3/q18_*.png` compares four treatments on three screens. *a* (consequence in the label) is smallest but drops nuance on cards ("Start over with a new plan" loses "it may ask you to approve"); *b* (one sentence by the group) reads as form text and detaches the consequence from its button; *c* (every action a row) is clearest but heavy for the fixed bar; for the bar, *c* needs an extra tap (an *Answer…* sheet) | **d:** in a card, an action that changes something is a row — verb, then one line of what it does; a harmless one (Explain) stays a compact button. In the fixed answer bar, the label carries the outcome (*Approve & run · Send back · Reject & cancel*; the full consequence is in the card above). Applied on desktop too, so the two devices say the same thing. S-21 ("no text under buttons") is read as "no caption under a button"; the text is part of the action | **Resolved** (proposed; reverses S-21's letter on the phone) |

---

## 3. Core and data mismatches

E's assumption → what Core does → what the design does now. Status: *fixed* (the design follows Core), *recorded*
(a Core behaviour the design can only describe), *open* (needs a decision).

| # | E assumed | Core | Design now | Status |
|---|---|---|---|---|
| M-1 | branches like `archeus/m-4c1e` | `archeus/msn_<26-char ULID>`; tasks `archeus/msn_….<key>`; only the single-mission read returns it | tail on rows, whole on the page; derived from the id on lists | fixed |
| M-2 | a mission has a start time and a short id | `created_at` only; executions carry `started_at`; no short id | "asked HH:MM" from `created_at`; the id's tail as the handle | fixed |
| M-3 | waiting = APPROVAL_REQUIRED or REVIEWING | a task, route or action approval leaves the mission BLOCKED or EXECUTING with a pending approval | waiting = any pending approval or review | fixed |
| M-4 | a failed check blocks a mission | VERIFYING → REPLANNING (automatic); BLOCKED only when no re-plan is left (`max_replans` 2) | the example and the chain follow it; the chain walks back to the re-plan cause | fixed |
| M-5 | a crashed agent fails the mission | the task fails retryably → REPLANNING → new plan (the replay's crash completed on its second plan); FAILED is reserved for "unrecoverable" | FAILED kept as a rarer state | recorded |
| M-6 | every EXECUTING mission has an agent on a step | it can be queued with no live execution | "waits for an agent to be free" | fixed |
| M-7 | approvals expire in minutes | plan, task, start: 24 h; action 2 h | "expires tomorrow 14:05"; *Next deadline* reads as rare (X.2 §12 proposed a window) | fixed; window open |
| M-8 | event names `approval.decided`, `mission.done`, `verification.passed/failed`, `execution.failed`, `mission.blocked` | `approval.state_changed`, `mission.state_changed`, `verification.state_changed`, `execution.state_changed`; ~10 mission moves each | the replay maps Core's names; the record lists only blocked, re-planning, failed, cancelled, completed | fixed in the replay; the fixture keeps its names |
| M-9 | the terminal state is DONE | COMPLETED | shown as "Done" | fixed |
| M-10 | plan order = array order | Core returns tasks by key; order is the `depends_on` graph | step N of M from the graph | fixed |
| M-11 | a repository has a default branch | never written (lv2-dr3) | not shown anywhere | fixed |
| M-12 | the model is always known | null for some harnesses | the agent line names the harness only | fixed |
| M-13 | a checkpoint says how many files | the event names execution and task only | "saved a checkpoint" | fixed |
| M-14 | the approval's consequences are the client's words | Core writes them: `presented.consequences` {approve, reject, request_changes} | the bar reads Core's words when present | fixed (useful) |
| M-15 | a mission started while stopped is BLOCKED and resumable | production: stuck in REASONING with no edge, also after the re-arm; via Tell: no mission at all | copy says "kept, not read" | **recorded (Core defect; P20 O1)** |
| M-16 | a declined request explains itself | the reply text says "no harness that can make the call is installed" while the cause is the stop | the design reads the intent's reason | **recorded (Core defect)** |
| M-17 | an expired approval stays visible | the attention list drops it with no event | the mission page and *Blocked or failed* still show it | **open (Q14d)** |
| M-18 | E's controls are the whole command set | Core also has per-mission **pause**, **stop this mission** (→ BLOCKED), **reprioritise**, pause all / resume all — E draws none | not added (no feature beyond the brief) | **open**: a running mission page offers nothing but the global stop |
| M-19 | a mission's "what you asked" is the user's words | a mission made by `POST /v1/missions` has no message | falls back to the objective | recorded |
| M-20 | ideas are in the replay | capture needs the brain's intent call | none in the replay | recorded |

---

## 4. Real-data replay

`tools/lvx_replay.py` runs the real Core runtime in-process (the judge's `TempCore`: workers, policy, state
machines, the fake harness and the scripted verifier), registers three git repositories as projects, and drives a
small afternoon through the API: a mission to completion, one whose agent crashes, one whose checks keep failing,
two look-alikes in one project, and a deploy plan left waiting. Every read the prototype makes — missions (list and
single), plans, verifications, timelines, approvals, `/v1/status` live work, events, ideas, harnesses — is written
verbatim to `lvx/replay.js` (only the scratch home path is redacted). `lvx/e2replay.js` turns it into the fixture's
shape and nothing else; anything E asks for that Core did not return is left out and listed (`?corpus=core`).

**What Core produced:** one COMPLETED; the crash re-planned itself and also COMPLETED (M-5); the failing checks
re-planned twice and ended BLOCKED "no replan left for this mission · 2 of 2 replans used"; the look-alikes
EXECUTING, one with an agent and one **queued** (M-6); the deploy plan APPROVAL_REQUIRED, expiring **tomorrow**
(M-7), with `step_up: true` and Core-written consequences (M-14).

**Did E survive?** Its structure did: overview, groups, the line, the error component, the approval component and
the project page all render from real reads with 47 known and 26 derived facts on the overview and no invented
one. Its content did not, until fixed: six things printed wrongly or not at all on first contact — a clock "38:05"
for a 24 h expiry, "undefined" for a READY task, "null" for a model and for a default branch, a *Blocked* caption
that said "check failed" for a block that was about re-plans, and a running tile with no agent. Each is fixed, and
the capture gate now fails on each (§A).

**Where the design still assumes data Core does not give:** the user's own words for a mission made outside the
conversation (M-19); named checks and exit codes (the scripted verifier records none — the real verifier does, so
this is a replay limit, not a Core gap); a checkpoint's file count (M-13); ideas (M-20); and, already tagged
since X.2, the repository of a multi-repo project (DR-3), the remote (DR-2), the environment (DR-4), the check
output (DR-8), the current operation (DR-6).

---

## 5. Desktop review

Seen in the desktop shell itself (QtWebEngine, as `archeus gui` embeds it; `results/lvx/qt/`, 24 screens, every
layout within 2 px of Chromium horizontally) and in Chromium at 1,440 × 900. Owner/design review, not a study.

| Question | Verdict | Failures found |
|---|---|---|
| Does it feel like an application? | **Yes.** Persistent places and projects, one top bar, modal Tell, the same frame on every page | the left bar marks *Missions* while the back link says *Overview* when a mission is opened from the overview |
| Do I understand what Archeus is doing within seconds? | **Yes.** "Meanwhile Archeus is working on 2 missions"; the right column is titled by it; each tile names the agent and its step | the *2 running* pill counts a queued mission that has no agent yet (real data) |
| Do I know what requires my attention? | **Yes.** One statement, waiting first, step approvals now included, a badge | *Next deadline* is amber for a 24 h plan approval; urgency is diluted |
| Can I distinguish similar missions? | **Yes** in one project (objective) and across projects (monogram and name) | two look-alikes with similar objectives would fall back to an opaque branch tail |
| Do buttons tell me what will happen? | **Yes** for every state-changing action in a card and every answer label | *Start…* on an idea and *Explain* still rely on a tooltip on desktop |
| Calm without feeling empty? | **Yes** on the overview; the mission page is dense but ordered | the step approval is six labelled blocks for one yes/no |
| Explains itself without becoming verbose? | **Mostly.** | gap tags ("requires DR-8") and source chips are prototype provenance and add noise; production would drop most of them |

## 6. Phone review

**Limit stated plainly:** no physical phone was available to this review. It was done at 390 × 844, DPR 2, touch and
mobile viewport in Chromium, on the nine screens the brief names (overview, missions, running work, approval, error,
project, idea, stopped/resume, notification entry). An emulator cannot judge thumb reach, safe areas, glare or
real scrolling; the owner's own pass on a phone is still owed (§0).

| Question | Verdict | Failures found |
|---|---|---|
| Does it feel like an actual application? | **Yes.** Tabs, pushed pages with a named back, a fixed answer bar, bottom sheets for the PIN | — |
| Designed for a phone? | **Mostly.** Answers within thumb reach, 44 px targets (gated), the strip above the tabs | the error page is about four screens long; the cancel command shows a raw `msn_…` id in Tell |
| What is Archeus doing, within seconds? | **Yes** on root places (the strip sentence); on a pushed page the head sentence says it | the overview's counter says *Running* where everything else says *working on* |
| What requires my attention? | **Yes.** The statement, the badge, Waiting first | — |
| Can I distinguish similar missions? | **Yes.** The objective wraps to two lines on a look-alike | — |
| Do buttons tell me what will happen? | **Yes.** Rows in cards, outcomes in the bar, the PIN step said before approving a deploy | — |
| Calm without empty? | **Yes.** | the safety line "Working normally" sits beside "Archeus is working on…" — two meanings of *working* |
| Explains itself without verbose? | **Mostly.** | the consequence rows add about 60 px per action; acceptable for two actions, not for more |

## 7. Remaining UX problems

1. **Cancel through Tell** is truthful but indirect, and its message is an id. A cancel route would remove both (Q14a).
2. **A failed mission is a dead end** apart from cancelling (Q14b).
3. **An expired plan approval strands its mission**, and Core's attention list forgets it (Q14d, M-17).
4. **Tell while stopped** cannot make work, and Core's own reply misattributes why (M-15, M-16).
5. **No per-mission control while running**: Core has pause and stop-this-mission; E offers only the global stop (M-18).
6. **"Working normally"** (the safety line) collides with "Archeus is working on…"; the safety wording could change without changing P20's semantics.
7. **Urgency colour** for 24 h deadlines (X.2 §12): *Next deadline* should appear only within a stated window.
8. **The running pill counts queued missions** as running.
9. **Navigation marks Missions** for a mission opened from the overview.
10. **Approval density**: the step and plan approvals stay six blocks on the twentieth repetition.
11. **Motion**: unchanged and unreviewed by a person; the head-or-fill question from X.2 §10 stays open. Nothing in X.3 added motion.

## 8. Recommendation

**NOT READY FOR LV2-2.** Against the brief's eight questions the corrected E now answers what Archeus is (the first
run, and the agent named at work), what it is doing (verbs, the agent, the step, the queue), what needs you (every
pending approval), what happened (outcomes and the record), what is known and unknown (unchanged, and now checked
against real reads), what each important action does (on the action), and which work you are looking at (look-alikes
told apart by what they are for). It does not yet have the owner's decisions on the controls that depend on Core
(Q14a, b, d), the resume rule (Q12/V2-3), or the notification brief (Q16) — and no person other than the author has
used it, on a real phone or otherwise. Authorise LV2-2 after those decisions and one owner phone pass; neither needs
another design phase.

---

## A. Evidence and files

| Gate | Result |
|---|---|
| Capture gate, E (`check_e2.txt`) | **172 of 172** (86 states × 2 devices; X.2 had 66). New rules: a button Core has no move for ("Ask Archeus to fix it", "Cancel mission", "Unblock and run again"), X.2's branch form, "undefined", "NaN", "null", a clock past 23:59, a PIN on the phone's resume page today, a retry offered on a failed mission; and *required* text for the new rules (step approval, start over, look-alike objectives, kept-not-read, queued, notification) |
| Mutations (`mutate_e2.txt`) | **17 of 17 killed** (X.2's 8 plus 9 for X.3). The first run let one survive: the clock rule had been written through a shell here-document that turned `\b` into backspace characters, so it could never match. Found by the mutant, fixed, re-run |
| Motion (`motion/check.txt`) | 11 of 11; nothing new moves |
| Desktop shell vs Chromium (`qt/check.txt`) | 24 of 24 |
| A–E unchanged | all 139 captures and their check files byte-identical (149 files) |
| Q17 (`x3/q17.txt`, `x3/q17_*.png`) | the strip clears content in 14 of 14 cases |
| Q18 (`x3/q18_*.png`) | the four treatments on the error, the stopped-then-resumed mission, the answer bar and the answer sheet |
| X.2 defect found | X.2's three phone captures of Tell showed the overview: the phone ignored `tell=`. Fixed; the phone Tell is its own page |

| File | Content |
|---|---|
| `prototypes/v2-later/lvx/e2.js`, `e2.css`, `e2fx.js` | the corrected E |
| `lvx/replay.js`, `lvx/e2replay.js` | a real Core's reads and the adapter (`?corpus=core`) |
| `tools/lvx_replay.py` | produces `replay.js` from an in-process Core |
| `tools/lvx_shots.py`, `lvx_mutate_e2.py`, `lvx_motion.py`, `lvx_qt.py` | the gates, extended |
| `tools/lvx_q17.py`, `tools/lvx_q18.py` | the two comparisons |
| `lvx/gallery.html` | opens on *E · LV2-X.3*; *E refined · LV2-X.2 (archived)* beside it |
| `tools/serve_lan.py` | for the owner's phone pass: one session, a random token, private network only |

---

## 9. LV2-X.4 — the owner's decisions, applied

The owner froze direction E (Overview · Missions · Ideas · Projects · Control; desktop safety bar with Tell and
Stop, persistent left navigation with projects, mission lines on Missions only; phone bottom tabs, pushed pages
with back, the running-work strip, full-page approvals, no modal-sheet approval) and decided Q12–Q18 below.
LV2-1 is not reopened. P20 is not changed: Core-down stop authority stays with the tray and `archeus estop`, no
new work runs until re-armed, a re-arm counts only once Core confirms it, the two-press protection and every
authentication and credential boundary stand.

### 9.1 Q12–Q18

| Q | Decision | What the UI does | Dependency |
|---|---|---|---|
| **Q12** Resume and the PIN | Today's Core is authoritative. No device asks for a PIN to resume. A PIN appears on the phone only where P20 built one: approving step-up work (a deploy) from a paired phone. D10's PIN on resume is shown only as a separate, labelled future state | Desktop Control: "Resuming from this computer does not ask for a PIN." No primed, stopped or resume copy on the desktop mentions a PIN. Phone Control and the phone's Resume page: "Resuming from this phone does not ask for a PIN." D10 is drawn only with `?pin=d10`, tagged *approved, not built*; production shows no future-PIN copy until D10 exists. Approving a deploy from the phone says "This phone asks for your PIN before it approves" and opens the PIN sheet | **P20 V2-3** (p20-design-gate.md:1029): device-specific copy, or D10 widened to the desktop. D10 itself is approved and **blocked** on V2-3 (:937); its build is P20's own slice. When D10 ships, the phone copy changes; if V2-3 widens D10, the desktop copy changes too. This amends the reassessment's SS-4 and SS-6, which said "resuming needs a PIN" on every surface |
| **Q13** The stopped state | Keep "Nothing runs until you resume." A request sent through Tell while stopped is not accepted; the UI says so and asks for it again after resuming. No different backend behaviour is designed | Before sending: "Archeus is stopped. Commands such as “cancel” still work. A new request is not accepted while stopped: send it after you resume." After: "Not accepted: Archeus is stopped, so it did not read this request and made nothing from it. Send it again after you resume." Control: "…A request you send meanwhile is not accepted; send it again after you resume." The answer reads the intent's recorded reason (`unavailable: emergency stop`, `calls.py:105-107`), never Core's reply text. X.3's "kept, not read" is withdrawn: *kept* suggested it would be acted on later | **V1/Core defects** M-15 and M-16 (§9.4). P20 unchanged |
| **Q14a** Cancel | No dedicated cancel API is claimed | **Cancel…** opens Tell with `cancel msn_…` (the id, because a title is ambiguous between look-alikes); its row says "Opens Tell with “cancel”; the mission ends when Archeus reads it." | Optional **data-contract**: a cancel route (`routes.py:35` lists it as deliberately absent) |
| **Q14b** Fix / retry | Only what Core exposes | Blocked: **Run again** (held from EXECUTING or VERIFYING, or by the stop: same plan) or **Start over** (otherwise: plans again and may ask for approval), both `POST /v1/missions/{id}/resume`. Failed: no button; "Archeus will not retry it on its own, and retrying it from here is not possible yet. You can cancel it." No note field. *Ask Archeus to fix it* is gone, and the capture gate fails if it returns | **Data-contract**: retry for FAILED (`FAILED → replan` exists, nothing fires it); DR-9 (a note to the agent, *Explain*) |
| **Q14c** Start on an idea | A Tell-prepared request | **Start…** opens Tell with "Make the idea “…” a mission." On the idea's page it is an action row: "Opens Tell with a request to make it a mission. Nothing starts until you send it." | **Data-contract**: DR-10 / Q10 (idea routes) |
| **Q14d** Expired plan approval | Represent it as it is; flag Core | "Nobody decided plan v1 by 15:52. Nothing ran. Archeus does not ask again on its own, and this mission stays here until you cancel it." Tagged *what happens next is not defined · Core*, with Cancel…. It stays under *Blocked or failed* and on the mission page because the client reads it from the mission list and the expired approval, not from Core's attention list | **V1/Core defect** M-17; a **Core decision** on what follows an expiry (§9.4) |
| **Q15** Look-alikes | Identity is **title · project · branch**, with the objective when it tells missions apart. A branch is a technical handle, not a human identifier | Every row: title, project monogram and name, then the branch tail (`archeus/…XFPC`) in the quietest text colour. A look-alike (same title, same project) adds its objective under the title (one line on desktop, up to two on the phone) and "asked HH:MM" when the times differ. The mission page shows the whole branch in Context. Across projects the project tells them apart (the stress day has *Upgrade the auth library* in two) | **Data-contract**: a readable mission handle. Core has the ULID and nothing shorter. Until then, two look-alikes with similar objectives asked in the same minute are told apart only by the branch tail; that limit is recorded, not designed around |
| **Q16** Notifications | Approvals and the emergency stop only. A notification never answers anything; a tap opens the mission, which says what changed. Blocked missions and titles in a push are P21's | Phone push: "A plan waits for your approval · Tap to open the mission". It names no mission and no project, so the wording stays valid whatever P21 decides. The desktop's own notification stays on the computer and names the mission. The landing says "Opened from a notification sent at 14:58 · Since then you approved it, at 15:12". X.3's dashed *Blocked* notification is no longer drawn | **P21**: whether a blocked mission notifies; whether a mission title may leave the computer in a push. No P21 gate exists yet (D8) |
| **Q17** The phone strip | Keep it. The safety line and the work line use different words. A queued mission is not "worked on" | Safety: **"Not stopped · accepts new work"** (was "Working normally"). *Working on* counts only missions with a live execution. A mission that is EXECUTING with no live execution is **queued** and named apart: strip "Archeus is working on 1 mission · 1 queued / Update the currency formatter · step 1 of 2"; only queued: "1 mission waits for an agent"; overview "Archeus is working on 1 mission · 1 queued for an agent"; pill "1 running · 1 queued"; a *Queued for an agent* group; a *Queued* chip. What waits for you never enters the strip's count; the Missions badge directly below it carries that. The strip is absent when nothing is running or queued, when stopped, offline or loading. The primed stop counts only the missions the stop would end (`executions.py:418-433` ends live executions only) | None. *Queued* is derived from `/v1/status` live items and the mission state. Optional **data-contract**: an explicit queued state |
| **Q18** Button consequences | X.3's treatment *d* | In a card, an action that changes something is a row: the verb, then one line of what it does. In the fixed answer bar the label carries the outcome (*Approve & run · Send back · Reject & cancel*). *Start…* on an idea's page now follows the rule; harmless actions stay compact buttons. This changes the letter of S-21 ("no text under buttons") where a phone action needs it | None |

### 9.2 The six replay inconsistencies

| # | Inconsistency | Resolution in the prototype |
|---|---|---|
| 1 | "Working normally" beside "Archeus is working on…" | The safety line says **Not stopped**; *working* belongs to work only (SS-1's wording amended, P20's states unchanged) |
| 2 | The running count included a queued mission | *Working on*, the pill, the counter tile and the primed hint count live executions; queued is counted and named apart |
| 3 | Amber *Next deadline* for a 24-hour expiry | Amber and *Next deadline* only within **2 h**, the shortest life Core gives an approval (an action). The fixture is now Core-true: every plan, task and start approval expires 24 h after it was asked; the one near deadline (*Upgrade the auth library*, 15:52) was asked yesterday |
| 4 | The left bar marked Missions for a mission opened from the Overview | The left bar keeps the place the page was opened from (Overview, or a notification → Overview; a project → Projects and that project), as the back link names it |
| 5 | Branch names as human identifiers | §9.1 Q15 |
| 6 | Wording that claims what Core does not do | Withdrawn: "kept, not read" (Q13); a phone push naming the mission (Q16); "Archeus re-plans with your note" on sending a *result* back: a review's note is stored, but the re-plan reason Core passes on is the review id (`verification.py:531-537`), so it now says "Archeus plans it again"; the expired approval's tag now names Core rather than "undecided" |

### 9.3 Evidence

| Gate | Result |
|---|---|
| Capture gate, E (`check_e2.txt`) | **174 of 174** (87 states × 2; one new state, a mission opened from the overview). New rules: "Working normally", "kept, not read", a phone push naming a mission, *Next deadline* or "working on 2 missions" on the real-Core overview, a clock before midnight, the left bar's place for four journeys; required "Not stopped", "Not accepted", "1 queued", *Next deadline* on the fixture's desktop overview, Start…'s consequence |
| Mutations (`mutate_e2.txt`) | **24 of 24 killed** (X.3's 17, two retargeted at the changed lines, plus 7 for X.4) |
| Motion | 11 of 11; nothing new moves |
| Desktop shell vs Chromium | 24 of 24 |
| A–E | untouched: no file they render from changed (`e2fx.js` is a no-op off `d=e2`; every `e2.css` rule is scoped to it) |
| X.3 captures | archived in `results/lvx/x3cap/`; the gallery opens on *E · LV2-X.4* with X.3 and X.2 beside it |

### 9.4 Dependencies, by owner

**V2 design work**
- ~~The owner's real-phone pass (§9.5).~~ Done and approved, see §9.7.
- The LV2-2 plan ([ARCHEUS_V2_LATER_UI_LV2_2_PLAN.md](ARCHEUS_V2_LATER_UI_LV2_2_PLAN.md), 2026-10-05) predates E. It builds LD-2's three places under V1's names (S1), leaves the phone to LV2-3, and says re-arm goes "through P20's step-up" (S7, §4), which Q12 now contradicts. It has to be rewritten for E, with its §8 questions (Q1 the V2-U0 human gates, Q2 P26 ordering) asked again, before LV2-2 can be authorised against it.
- Not blocking: the step and plan approvals stay six labelled blocks (X.3 §7.10); the mission-line motion question (head or fill) is open since X.2 and belongs to LV2-4.

**V1/Core defects**
- **M-15** A mission created while stopped through `POST /v1/missions` stays in REASONING with no edge out under a production brain, also after the re-arm (`calls.py:105-107`, `planning.py:129-137`). Gate item 5's BLOCKED result holds only for the stub brain.
- **M-16** A request declined because of the stop gets the reply "no harness that can make the call is installed" (`conversation.py:346-359`); the intent's reason is correct.
- **M-17** An expired plan approval leaves its mission in APPROVAL_REQUIRED with nothing pending, and the attention list drops it without an event.
- An expired **action** approval: the mission's end state is pinned by no test (p11 and the code disagree).

**P20 decisions**
- **V2-3**: who needs a PIN to resume. It unblocks D10's build. V2's copy is device-specific for today's behaviour only and chooses neither answer.
- Unchanged and still P20's: Q3, the "armed" wording in V1's `armedText` and Core's policy reason. V2 surfaces never show the word.

**P21 decisions**
- Whether a blocked mission notifies.
- Whether a mission title, or a project name, may leave the computer in a phone push.
- P21 owns notifications as a whole (D8); no P21 gate exists yet.

**Future data-contract work** (none needed for LV2-2's honesty; each removes a workaround)
- A cancel route (Q14a); retry for a FAILED mission (Q14b); DR-9, a note to the agent and *Explain*; DR-10, idea routes (Q14c, Q10).
- A readable mission handle (Q15).
- What follows an expired plan approval, and an event when the attention list drops one (Q14d).
- Optional: an explicit queued state (Q17).
- Already recorded: DR-1 (project name, client join), DR-2 remote, DR-3 multi-repo, DR-4 environment, DR-6 operation, DR-8 check output.

### 9.5 The phone pass

`py prototypes/v2-later/tools/serve_lan.py` (add `--adb` for Android over USB) prints a one-session *LV2-X.4
phone pass* address on the private network. It opens `lvx/pass.html`: nine links, each to a live screen of `?d=e2`.
The pass is a product check, not a study. On each screen the question is the same: without help, can you tell
what Archeus is doing and what it needs from you?

| # | Screen | Look for |
|---|---|---|
| 1 | Overview | Is *Not stopped* read as the safety state and not as a status of work? Does the one amber *Next deadline* (40 min) stand out from the three that expire tomorrow? Do the strip and the badge together say "working on 2, 4 wait for you" without reading the page? |
| 2 | Missions, a busy day (`corpus=x2`) | Can you tell the two *Update the currency formatter* in invoicing apart from the objective alone? Is the branch tail ignorable? Does the list scroll like an app's list? |
| 3 | Running work, real Core data (`corpus=core`) | Does the strip read "1 working, 1 queued" at a glance? Tap it: is the queued mission's page clear that no agent is on it yet? |
| 4 | An approval | Is the fixed answer bar in thumb reach, and do *Approve & run · Send back · Reject & cancel* say what happens without the card above? Does *Approve & run…* asking for the PIN feel expected? |
| 5 | A blocked mission | Is "why it is blocked" readable before the actions? Do *Start over* and *Cancel…* say enough? Is opening Tell with `cancel msn_…` acceptable as the way to cancel? |
| 6 | A project | Does the board read as "where each mission stands" on a narrow screen? Is the way back obvious? |
| 7 | An idea | Is it clear that *Start…* prepares a message and does not start anything? |
| 8 | Stopped, then resume | Does the red frame feel like a state of the whole app and not a banner? Is *Resume work…* findable, and is "does not ask for a PIN" reassuring or alarming? |
| 9 | From a notification | Three pushes name no mission: is that acceptable on a lock screen? After a tap, does the mission say why you are there and what changed? |

Across all nine: does it feel like a phone application (tabs, pushed pages, back, nothing that needs hover)?
Is it minimal without feeling empty? A structural problem found here is fixed in the prototype before LV2-2;
the criteria are not relaxed to close the phase.

### 9.6 Exit condition and readiness

| LV2-X closes when | State |
|---|---|
| Q12–Q18 explicitly resolved | done (§9.1) |
| The prototype reflects them | done (§9.2, §9.3) |
| The real-Core replay has no unexplained UI claim | done: every fact on the seven replay screens carries its source, and each gap is listed (§4, `?corpus=core`) |
| The nine-screen real-phone pass | done: two findings fixed, approved by the owner (§9.7) |
| Core, P20 and P21 dependencies recorded | done (§9.4) |
| No open question turned into a product promise | done: PIN, cancel, retry, idea start, expiry and notification content each say what exists today and tag what does not |

**NOT READY FOR LV2-2.** One blocker: an LV2-2 plan that describes E (the current one describes LD-2), with its
§8 Q1 and Q2 asked again. It needs no design work; the design side of LV2-X is closed.

*2026-10-07:* the LV2-2 plan is rewritten on E ([ARCHEUS_V2_LATER_UI_LV2_2_PLAN.md](ARCHEUS_V2_LATER_UI_LV2_2_PLAN.md)).
The old Q1 and Q2 are re-asked there as G-3 and G-1/G-2. It awaits the owner's authorisation.

### 9.7 LV2-X.5 — the phone pass

The owner ran the pass on a real phone over `serve_lan.py`. The owner reported two findings and approved the
result after they were fixed. The per-screen questions of §9.5 were not answered one by one, and nothing structural
was reported (places, tabs, pushed pages, the answer bar, the strip). The pass closes on the owner's approval, not
on a scored study.

| Finding | Fix |
|---|---|
| "The save idea button should be on the right" | Every two-button row (`.x-fixrow`: Save idea, Send, Approve after the PIN, Resume work, Open the mission) now reads Cancel first and the confirming action last, in markup as well as on screen, so focus order matches what is seen. On the desktop the row sits at the dialog's right edge. |
| "Really enlarged … claustrophobic", then "still too big" | The phone kept a type scale one step above the platforms' defaults and 48–60px controls. It now uses the dense end of both scales: body 13/18 (iOS Footnote), row titles 14/20 (M3 Title Small), captions 12/16 (iOS Caption 1), labels 11 (Apple's minimum), page titles 20/25 (iOS Title 3). Buttons are 40px (M3's standard button) and stay ≥ 44px wide, so the hit area meets the HIG's 44pt and well clears WCAG 2.5.8's 24px. Top bar 56 → 48, tab bar 60 → 50, strip 52 → 42. Eight texts with a fixed 14–15px size now follow the scale. Inputs stay 16px, because below that iOS Safari zooms on focus. Section spacing grew while sizes shrank. |

Found on the way: `.x-mt` was both the mission-title class and a 14px top-margin utility, so every mission title in
a list sat 14px low (desktop too). The margin rule is now `.label.x-mt`. On the phone, an empty stage of the
project board is one line instead of a block.

The sources behind the numbers: the M3 type-scale tokens (`TypeScaleTokens.kt` in androidx), Apple HIG Typography
and Accessibility, Material density guidance (m2.material.io, *Applying density*), WCAG 2.2 §2.5.5 and §2.5.8, and
Primer's typography tokens.

| Gate | Result |
|---|---|
| Capture gate, E | 174 of 174; the touch-target rule (≥ 32px tall and ≥ 44px on one side) holds at 40px buttons |
| Mutations | 24 of 24 killed |
| Motion | 11 of 11 |
| Desktop shell vs Chromium | 24 of 24 |

Not changed, offered to the owner: each waiting card on the phone overview still gives *Review ›* its own line.
