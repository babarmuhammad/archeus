# Archeus later-V2 UI — LV2-0 evidence phase record

**Status: EVIDENCE RECORDED — NOTHING IS DECIDED.** This is the phase record for **LV2-0
Evidence**, the first phase of the later-V2 roadmap
([ARCHEUS_V2_LATER_UI_RESEARCH.md](ARCHEUS_V2_LATER_UI_RESEARCH.md) §21, cited as *LR*). It tests
whether the later-V2 direction is actually better before any of it becomes a design rule, an ADR
or a production phase. It ends at the user's decision list (§14). Every LD-n stays open until the
user decides it.

- **No production code changed.** No V1 file, no Core, no API contract, no `clients/app` file,
  no V2 production code. Everything built lives in `prototypes/v2-later/` (lab, tools, results).
- **No earlier decision is overwritten.** Where a result here disagrees with an accepted V2-U0
  decision ([ARCHEUS_V2_UI_ARCHITECTURE.md](ARCHEUS_V2_UI_ARCHITECTURE.md), cited as *A*), A
  stands and the disagreement is listed for the user (§14.2).
- **Sources of truth for terminology, matrices and registry:** *LR*, the reference study
  ([ARCHEUS_V2_LATER_UI_REFERENCE_STUDY.md](ARCHEUS_V2_LATER_UI_REFERENCE_STUDY.md)) and the
  proposed rulebook ([ARCHEUS_V2_LATER_UI_RULEBOOK.md](ARCHEUS_V2_LATER_UI_RULEBOOK.md)).
- **The central conclusion is kept and was tested, not assumed:** *the biggest missing piece is
  information design, not more visual effects.* §3 says how far the evidence supports it.

Date 2026-10-05. Branch `archeus-v1-rearchitecture`.

## Contents

0. Status vocabulary · 1. The decision table · 2. Method, rig and limits · 3. Results at a glance ·
4. Information architecture proposal · 5. Mobile architecture proposal · 6. Mission / project /
repository context proposal · 7. The day's light · 8. The motion middle · 9. Budget (LD-1) ·
10. Accessibility results · 11. Performance results · 12. V1 defects found (reported, not fixed) ·
13. Revised later-V2 roadmap · 14. Proposed production changes, and the decisions that need you

---

## 0. Status vocabulary

Every proposal in this record carries exactly one **status**:

| Status | Meaning |
|---|---|
| **Accepted (V2-U0)** | Already decided by the user in A §T; this phase builds on it and does not reopen it |
| **Proposed (research)** | Proposed by *LR*; not tested here, or tested only indirectly |
| **Needs prototype evidence** | Must be prototyped before anyone can decide; prototyped here unless marked owed |
| **Needs human testing** | The automated evidence is in; the gate is a person |
| **Rejected / deferred** | Rejected by evidence, or deferred to a later phase with its reason |

and, for the LD-n decisions, **flags** for what each still needs: *prototype*, *measurement*,
*human test*, *architecture/API change*, *production-ready*, *reject*, *defer*.

## 1. The decision table

The opportunity ids are *LR* §19's. "This phase" is what LV2-0 did; "evidence" points to a record
in `prototypes/v2-later/results/`.

| Id | Proposal | Status before | This phase | Evidence | Status after |
|---|---|---|---|---|---|
| — | No orb, no fake telemetry, no permanent glow, no decorative neural graphics, no render loop for spectacle, no animation without an event, the thread as the signature light, figures as geometry, spatial transitions (no View Transitions in Qt), depth without blur or scaling, Display typography, reduced motion resolves to a calm complete state | Accepted (V2-U0) | Held in every prototype; each is either inherited or re-checked (idle invariant, transform/opacity audit, forced colours) | `le1`, `le3`, `le5` | **Accepted (V2-U0)**, unchanged |
| O-1 | Now hierarchy rebuild | Proposed | Prototyped (A/B/C) | `le1` | **Needs human testing** (5-second test) |
| O-2 | The decision surface | Proposed | Prototyped (desktop pane, phone page) | `le1`, `le4` | **Needs human testing** (comprehension) |
| O-3 | Phone IA: three places + strip + header e-stop | Proposed | Prototyped | `le4` | **Needs human testing** (physical phone) |
| O-4 | Human-language layer | Proposed | Prototyped on V1's own strings | `ld9-voice` | **Needs human testing** (comprehension); ready to fold into V2-U2 if approved |
| O-5 | Response micro-interactions (press, reveal, summon 0 ms, focus advance, keystroke safety) | Proposed | Prototyped and measured | `le5` | **Needs human testing** (feel); automated gates pass |
| O-6 | Peek → panel → page | Proposed | Partly: C's pane is the panel; Space-peek not built | `le1` | Needs prototype evidence (owed) |
| O-7 | Causality in context (chips, because-chain) | Proposed | Because-chain prototyped **from the Verification record only** | `le1`, `le2` | Rejected / deferred: cross-mission causality waits for P21 |
| O-8 | Verification as evidence | Proposed | Prototyped (checks on page and inspector) | `le1` | Needs human testing |
| O-9 | The day's light | Proposed | Three representations prototyped and measured | `le3` | **Needs human testing** (cold test + two-week diary) |
| O-10 | Row traces | Proposed | Absorbed into the day's light R3 | `le3` | Folded into O-9 |
| O-11 | Wide-desktop composition | Proposed | Prototyped (C at 1,100 / 1,700) | `le1` | Needs human testing |
| O-12 / O-13 / O-14 | Escalation by recorded wait; auto-decided log; post-review tail | Proposed | Auto-decided log sketched only (static) | `le1` | Proposed (research), unchanged |
| O-15 / O-16 / O-25 | Material refinement; scale contrast; numeric register | Proposed | Scale contrast used (verdict at display size); not measured separately | — | Proposed (research) |
| O-17 / O-28 | Relations re-scope, scrubbing; detachable window | Proposed | **Not prototyped**: honest causal data does not exist before P21 | §14 LD-6 | Rejected / deferred to LV2-5 |
| O-18 | OS presence (tray, title) | Proposed | Not built | — | Proposed (research); LQ-7 open |
| O-19 | Motion middle | Proposed | 14 primitives prototyped and measured in Qt and headed Chromium | `le5` | **Lean set: needs human testing; count, tooltip group, release deferred** |
| O-20 | Phone privacy; offline never queues | Proposed | Not built | — | Proposed (research) |
| O-21 | Week's light | Optional | Not built | — | Deferred (after O-9's diary) |
| O-22 / O-23 | Sound; haptics | Experimental / optional | Not built | §14 LD-10 | Deferred |
| O-24 | Passkey step-up | Proposed | Not built (P20 owns credentials) | — | Deferred to LV2-2 with P20 |
| O-26 | Static grain | Experimental | Not built | — | Deferred |
| O-29 | Warm neutrals + state balance | Optional | Measured, nothing changed | `le7` | **Needs human testing**; warm-at-70 not recommended |
| O-30 | Native phone shell | Experimental | — | — | Deferred (LQ-6) |
| R-1…R-10 | The research's rejects | Rejected | Re-confirmed where touched (grid-rows disclose measured and rejected again) | `le5` | Rejected |
| DP-1…DP-10 | **Design pass** (added after the first report, at the user's request): Apple HIG *principles* plus the installed design-audit, frontend-design, web-design-guidelines and typography skills, applied to B, C and the day's light. Presentation only; no glass, blur, motion or new colour | — | Audited (15 findings), applied in `lab/polish.css`, every probe re-run against the pre-pass results; `?dp=0` renders the before | `le8` | **Proposed (design pass)**; needs human testing (runs inside H-1…H-3); D-5 |

## 2. Method, rig and limits

**Lab.** `prototypes/v2-later/lab/`: `ia.html` (LE-1/2/4; `?v=a|b|c`, `?ctx=v1|proposed`,
`?corpus=diag`), `light.html` (LE-3), `motion.html` (LE-5). Every page links the **V1 token
stylesheet itself** and reuses the V2-U0 engine (`lab.js`) and the accepted PR-5 figures
(`figures.js`), so prototypes are judged on the ground they would extend. The server
(`tools/serve.py`) binds loopback and serves exactly two read-only roots.

**Fixture.** `lab/fixture.js` — one synthetic Tuesday afternoon (10 missions, 3 projects, 46
events), **shaped field-for-field like V1's own reads** (§6). Anything V1 does not record is
marked `proposed:` and rendered only under `?ctx=proposed`. `?corpus=diag` reproduces the V1
diagnosis state (four approvals, nothing running) to **calibrate the V1 replica against the real
V1 capture**: replica phone Now **5,066 px vs real 5,590 px** (−9 %). The replica is conservative
— it under-states V1's length, so every phone improvement below is, if anything, understated.

**Variant A is a replica, not V1.** Composition, fields and strings are V1's (D-captures, the
surfaces' source); the data is the fixture. That keeps the comparison like for like: same facts,
three structures.

**Devices and environments.** Desktop wide 1,920 × 1,080, desktop 1,440 × 900, desktop narrow
1,024 × 768, phone 390 × 844 and small phone 360 × 740 (touch, DPR 2); dark, light, high contrast
(`prefers-contrast: more` + V1's `data-contrast`), forced colours, 200 % text, reduced motion;
reduced transparency is trivially satisfied (no prototype has a translucent surface — §10).

**Tools** (`prototypes/v2-later/tools/`): `ia_probe.py` (questions, heights, gates, targets,
e-stop reach, axe, 200 %), `light_probe.py` (provenance, idleness, coverage), `motion_measure.py`
(V2-U0's own Qt and headed-Chromium drivers, plus an Event Timing input pass), `budget.py`
(marginal cost with the SPA's own minifiers), `colour.py` (OKLCH), `filmstrip.py`,
`mutate_gates.py` (every lab gate killed its mutant — `results/mutate_gates.txt`).

**Limits, stated once:**

1. **The question measure is a structural proxy** — clicks, scroll distance and words read before
   the answer — **not time-on-task.** No person was tested. Every human gate is listed in §14.3
   and none is converted from a proxy.
2. **The data is synthetic.** It tests structure and language, not a real day's corpus.
3. **The machine was shared and under heavy load** from processes outside this session (a batch
   job using ~11 CPU-hours, another session's mutation run and e2e tests). Frame and CPU figures
   are therefore pessimistic; relative comparisons were taken in the same conditions.
4. **No physical phone.** Phone results are emulated (Chromium, touch, DPR 2).
5. **Qt** is the shipped shell (QtWebEngine 6.11, Chromium 140) on Intel UHD, as in PR-1…PR-6;
   input latency was measured in headed Chromium with real CDP input, not with native Qt input.
6. **V1 citations are against the working tree at `8fe7ce3`.** Another session was editing the V1
   e-stop UI (`clients/app/src/components/ui.tsx`, `state/present.ts`, `surfaces/Control.tsx`,
   new e-stop tests) while this phase ran. This phase changed none of those files; the citations
   in §6 and §12 were re-checked after those edits and still hold. The budget baseline is the
   built bundle in `archeus/api/static/assets`, which those edits had not rebuilt.
7. **The lab's contrast check reads only `rgb()` computed colours.** A `color-mix()` resolves to
   `oklab(…)` and is misread, which the design pass found (`le8` note 2). Every lab colour is now
   hex or `rgb()`, and production tokens must be too.

## 3. Results at a glance

| Question | Answer from the evidence | Record |
|---|---|---|
| Is the three-place IA better than V1's structure? | On the proxy, **yes on every question, on every device** — V1 needs scrolling or clicks for 6 of 8 questions on the phone; B answers 5 of 8 on the first phone screen with no interaction | `le1` |
| Does the responsive desktop (C) help? | It puts evidence beside the decision and holds everything on one screen at 1,440 and 1,920; it does **not** answer faster than B on the proxy (C's gain is the inspector being already open) | `le1` |
| Can the phone stop being thousands of pixels tall? | **Yes: 5,066 px → 844 px** for the diagnosis state (one screen), **4,336 → 1,206 px** for the busy fixture; e-stop visible on every screen; Back never exits | `le4` |
| Does V1 know enough to show mission/project/repo context? | **Mostly yes, and almost none of it is shown.** Missing from Core: remote/provider, operation inside a task, environment on the approval | `le2` |
| Is the day's light possible from real data only? | **Yes**: 0 drawn elements without a record across 54 renders; static; ≤ 3 ms | `le3` |
| Which day's light? | **R3 (ledger + traces)** answers all of "what was touched" with a shape; R1 lanes names no mission without hover | `le3` |
| Is the motion middle safe? | Yes in the measured forms: every interaction ≤ 1 frame input → paint, input mid-animation acts at once, idle after every event, transform/opacity only | `le5` |
| Is the information-design conclusion right? | **Yes.** The largest measured gains (questions, heights, machine strings 3 kinds → 0) come from structure, language and CSS costing ≈ 0–2.4 KB; motion and light add polish and identity on top, they do not answer the questions | `le1`, `ld9`, `le6` |
| Should the budget go to 16–18 KB? | **No.** ≈ 12.5 KB of visual behaviour, plus the information layer under the V1 bundle gate | `le6` |
| Does the design pass (HIG principles + design skills) improve it? | **On craft, yes; on the proxy, mostly neutral.** One leading edge, no orphans, quiet separators, list headers, a full-width Approve, a capsule tab, a floating strip. Clicks and words are unchanged everywhere; phone scroll is down on 4 of 5 questions; the small phone scrolls 6–14 px further; the phone decision page is 60 px taller. 0 axe / 0 contrast / 6 of 6 gates killed; 1.30 KB gross | `le8` |

---

## 4. Information architecture proposal

**Status: Needs human testing.** Prototype: `lab/ia.html?v=b` (and `?v=c` for the desktop
composition). Evidence: `results/le1-ia.md`.

**Three places, the same on every device; the composition differs per device.**

| Place | V1 destination it replaces | Holds, in this order | Answers |
|---|---|---|---|
| **Now** | Now | (1) the **verdict** at display size ("3 need you · 2 running · 2 stopped"); (2) one sentence naming the running work ("Fix the flaky date test (archeus) is on step 4 of 7: run the date suite 50 times."); (3) **Needs you**: ≤ 3 one-line Decide rows — verb, object, consequence, expiry, context line — with the primary verb inline on desktop; (4) **Running**, a departure board: figure, title, task · step N of M, project · branch · where, elapsed; (5) **Stopped**: figure, title, *because* from the record; (6) one line "Today: 2 verified · 1 failed · 1 blocked"; (7) "Since you looked" collapsed, in words | Q1–Q5, Q7 on the first screen |
| **Needs you** | Attention (a lens on Now) | Decide · Review · Unblock, each one line; "Decided for you by policy today" collapsed | Everything that needs a person, and what policy decided without one |
| **Missions** | Work | Grouped by state (Running, Needs you, Stopped, Upcoming, Done today), filter chips; World and Relations from here | Every mission, one line each |
| World, Control | World, Control | Unchanged; on desktop dimmed below the three places, on the phone behind the header menu | — |

**Rules the prototype implements and the probe checks:**

- The same decision is offered **once** per screen (V1 offers each approval twice on desktop Now:
  the card and the conversation — measured `dup_decisions = 2` on A, **0** on B and C).
- **No machine language at the first two depths** (V1 Now and Attention: ISO timestamps, policy
  grammar and policy enums; B and C: **none**). The raw record is depth three, mono, in a
  disclosure.
- Every needs-you item is decidable on the screen that shows it (rulebook §9).
- **One object, two depths built here** (row → pane/page); the third (Space-peek) is owed.

**The nav change is a data edit.** V1 has one navigation table (`clients/app/tokens/navigation.json`
→ `tools/gen_ui.py`) feeding sidebar, phone tabs, shortcuts, palette and TUI. The three places
are a relabel (Work → Missions, Attention → Needs you) plus World's `phone: tab → menu`. Whether
to **rename on desktop** is a decision (LR §10 proposed not renaming; the lab renamed, to test
the words) — §14.2 D-2.

**Desktop composition (C), container-driven:** < 1,100 px one column with the object as an
overlay; **1,100–1,700 list + object pane** (the first decision is open by default, so "what
needs me" and "what will happen if I approve" are on one screen); **≥ 1,700 list + object +
evidence inspector** (because-chain, verification checks, context — moved, not repeated). Prose
stays at ≤ 72–80 characters at every width.

## 5. Mobile architecture proposal

**Status: Needs human testing (physical phone).** Prototype: `lab/ia.html?v=b` at 390 × 844 and
360 × 740. Evidence: `results/le4-mobile.md`.

| Part | Form | Measured |
|---|---|---|
| **Header** (52 px, sticky) | Mark · compose (＋) · **Stop all** (two-step, LD-7) | E-stop visible without scrolling on **6 of 6** phone screens (V1: on **none** of the phone's first screens, D-4) |
| **Mission strip** (56 px, fixed above the tabs) | Two lines: running mission's title; "step 4 of 7 · 20 min · 1 more running". Tap opens the mission. Never collapses on scroll | Never truncates the step or the time; title ellipsis only below 360 px |
| **Three tabs** (56 px) | Now · Needs you (count) · Missions | Control moves to the header menu |
| **Rows** | Two lines at 390 px: *verb · object* / *project · consequence · expiry* | All targets ≥ 44 px after the fixes in `le4` |
| **Decision** | **A pushed full page**, not a sheet: verb as headline, the planner's summary (attributed), consequence, why it asks, decision context, what changed since the last version, context, the raw record at depth three; a fixed bottom bar **Reject · Ask for changes · Approve**, 58 px tall, 10 px above the edge; strip and tabs hidden underneath | Page owns a history entry: **Back returns to Now and never exits the app** |
| **Mission** | Pushed page: title, figure · state · context line, compact spine, "Now:" line, **vertical because-chain**, next actions (first focused), goal, verification checks, context | — |
| **Relations** | Not on the phone in portrait; the because-chain stands in | — |

**Heights** (same fixture, same device): phone Now **4,336 px (5.1 screens) → 1,206 px (1.4)**;
for the diagnosis state **5,066 px (6.0) → 844 px (1.0)**. Needs you 2,555 → 902 px.

## 6. Mission / project / repository context proposal

**Status: Proposed, with data requirements documented, not implemented.** Evidence:
`results/le2-context.md` (full inventory with file:line citations).

**Finding.** V1 Core records project, branch, commit, working directory, current task, step
order, verification and execution start. **Almost none of it reaches a row**: the project name is
never joined onto a mission; branch and head sit in a collapsed Details; the working directory is
never rendered; and the row status line is always empty because rows call `statusLine(m)` without
tasks (`Work.tsx:107`, a V1 defect, §12). Three facts are **not recorded at all**: the remote
(provider, owner/repo), the operation inside a task, and the target environment on the approval
(known at the action, dropped by `presented.what`).

**Proposal.**

1. **Four kinds of fact, always distinguished:** *known* (a Core field, plain), *derived* (computed
   by a stated rule, captioned "derived" with the rule on hover/focus), *proposed* (needs a data
   requirement; never shown until it exists), *unknown* (one quiet line "Not recorded by Core:
   remote, environment." — never a placeholder per field, never a badge).
2. **Density by depth:** a row carries **one line — project · branch**; the phone row carries the
   project only. The page/pane carries the full context block. On the 1,700 px composition the
   context lives in the evidence inspector, once.
3. **Sentences built only from fields.** "3 tasks · includes a deploy" (from `action_class` and the
   plan), not "deploys to staging" (Core does not hold the environment on the approval) — the
   prototype's own first draft got this wrong twice (`le2` §2).
4. **Data requirements DR-1…DR-7** (`le2` §3): project name joined onto reads; `Repository.remote_url`
   with provider/owner derived; a mission's repository link; environment kept in `presented.what`;
   the `LiveItem` fields typed and the row status line fixed; the current operation (P21); a
   per-day event read.

## 7. The day's light

**Status: Needs human testing.** Evidence: `results/le3-days-light.md`.

**Recommendation: R3, "ledger + traces"** — per project, each mission touched today as a sentence
(figure, title, outcome in words) led by a word-sized trace on one fixed day axis; the project
line says how many files changed. It is the only representation that answers *what did Archeus
touch today?* completely without interaction (3/3 projects, 10/10 missions, outcomes by shape and
word, when, files) and still has a shape. **R1 "lanes"** — the research's original form — is the
better picture but names no mission without a hover and reads as a Gantt chart; it is kept as an
optional World "day view". **R2** (the ledger alone) is the text mirror. All three: 0 elements
without a record; no animation; one scale across days (yesterday's two missions look like a quiet
day); outcome by shape in forced colours.

**Placement:** the "all clear" state of Now, the first open of the day (K-1's canvas), on demand
from World. Never a standing panel on a busy Now.

**Needs DR-7** (a per-day event read); today it would mean paging the whole event log. **Gates:** a
cold "what did it touch today?" test and the two-week diary (LR §18 kill criterion).

## 8. The motion middle

**Status: lean set needs human testing; three primitives deferred; one stopped.** Evidence:
`results/le5-motion.md`.

**Recommendation — the lean middle:** press, hover, reveal (all CSS; reveal via Popover + anchor
positioning + `@starting-style`, **verified in Qt 6.11**, which answers LQ-4), summon at 0 ms,
disclose/collapse by FLIP, confirm/refuse (the label becomes the result, the row recedes in
place, focus advances), push/pop for the phone's decision and mission pages (history-owned), a
120 ms peer crossfade by pointer and none by keyboard, and reorder without the spring. ≈ 1.49 KB.

**Measured:** in the real Qt shell on Intel UHD, every primitive p95 16.7–16.8 ms with max 16.8 ms
and the page fully parked after every job (one unexplained 592 ms long-animation-frame entry in
the tooltip job, not visible in any rAF interval). Input → next paint ≤ 1 frame for every
interaction in headed Chromium with real input, including clicks mid-animation; an input that
lands mid-animation ends all running animations in 0.1–0.2 ms before its own handler runs (F-5);
Enter pressed right after Approve decided the next row (keystroke safety). Every keyframe was
`transform` or `opacity`. Reduced motion: every primitive instant or a ≤ 160 ms fade, focus kept.

**Deferred** until a human test asks for them: count (0.32 KB), tooltip group (0.40 KB), release
with its spring (0.84 KB). Release is notable for a different reason: a gesture spring **does
not need the rAF loop** LR §11 assumed — sampled into WAAPI keyframes it is compositor-driven and
parks itself. **Stopped:** disclosure by `grid-template-rows` (≈ 6× FLIP's layout cost; it animates
layout). **No animation library** is needed for anything.

The principle held as measured: the frequent primitives (press, hover, summon, keyboard
navigation) have no travel at all; travel is reserved for the several-a-day spatial ones.

## 9. Budget (LD-1)

**Status: measurement done; decision needed.** Evidence: `results/le6-budget.md`.

- **The real V1 baseline today:** 146.6 KB gzip JS, 5.96 KB CSS (0.9 KB above A §Q's figure, all
  V1 work).
- **The real V2-U0 commitment is ≈ 9.2 KB, not 9.7.** Re-priced the way it would ship — minified by
  the SPA's own minifiers and gzipped *inside* the V1 bundle — the four fenced V2-U0 parts come in
  12–20 % below their recorded figures (PR-5 3.45 → 3.04 KB; PR-6 base 2.13 → 1.70; governor 1.47
  → 1.20; PR-4 0.24 → 0.21). PR-2/PR-3 are not fenced and keep their recorded values.
- **Almost free (each ≤ 0.6 KB, or net ≈ 0 because it replaces V1 code):** the three-place IA and
  both compositions (CSS), press 52 B, hover 31 B, reveal 217 B (**CSS only** — Popover, anchor
  positioning and `@starting-style` all work in Qt 6.11), the language layer 511 B, the e-stop
  two-step 320 B.
- **Genuinely costs:** context renderer 1.43 KB (most of it the provenance explanations, which
  could move to a lookup), the lean JS motion middle **1.49 KB** (full: 2.80), the day's light R3
  **1.57 KB**.
- **Not justified by any measure in this phase:** count (320 B), tooltip group (395 B), release
  and its spring (≈ 840 B), R1 lanes alongside R3 (1.65 KB).

**Recommendation:** not 16–18 KB. **≈ 12.5 KB of V2 visual behaviour** (≈ 9.2 committed + 1.5 lean
middle + 1.6 day's light), with the **information layer** (language, context, composition,
≈ 3 KB) **priced under the V1 bundle gate** as the product UI it is — it replaces V1 markup and
strings rather than adding visual behaviour. If one number is preferred, that is ≈ 15 KB all-in.

**After the design pass (`le8`):** the pass is **1.30 KB gross** and is product presentation, so
it joins the information layer under the V1 gate (≈ 3 → ≈ 4.3 KB gross, net lower once production
removes the rules it supersedes). The aligned day's-light axis moves R3 from **1.61 to 1.72 KB**.
The visual-behaviour figure stays **≈ 12.5 KB** (12.6). Gross all-in is ≈ 16.8 KB, which **is not
a case for raising LD-1**: the overage is restyled product CSS that nets against V1, not new
behaviour.

## 10. Accessibility results

*(completed below)*

## 11. Performance results

*(completed below)*

## 12. V1 defects found (reported, not fixed)

This phase does not touch V1. These are for V1's own follow-up:

| # | Defect | Where | Effect |
|---|---|---|---|
| V-1 | Rows call `statusLine(m)` **without tasks**, so the status line is always empty on Now and Work | `clients/app/src/surfaces/Work.tsx:107`; `state/present.ts:149-152` | "What is it doing?" is unanswerable from any V1 row (LE-1 Q1: 2 clicks in V1) |
| V-2 | `LiveItem.workdir`, `branch`, `task_title`, `waits_on` are served on every `/v1/status` and absent from the generated TS type, so never shown | `archeus/core/application/live.py:70-78`; `clients/app/src/api/generated.ts:564-580` | Context fetched and discarded |
| V-3 | The e-stop is in `.strip-more`, hidden on phones; no e-stop on any phone first screen | `App.tsx:597-604`; `styles/app.css:452-454` | Already known as D-4; recorded here because LD-7 depends on it |
| V-4 | The project name is never joined onto missions, attention items or the digest | `api/schemas.py:34,178,339` | Rows cannot say which project |

## 13. Revised later-V2 roadmap

Changes from LR §21 are in **bold**. Every production phase still waits for P26 and for the V2
phase it depends on, and ends at a gate with captures, mutation-verified checks, A §Q
measurements and the user's sign-off.

| Phase | Content | Depends on | Core / API work | Exit evidence |
|---|---|---|---|---|
| **LV2-0 Evidence** | This record | — | none | **Done (automated); human gates open (§14.3)** |
| **LV2-0b Human evidence** (new) | The 5-second hierarchy test (A/B/C), the decision comprehension test, the physical-phone thumb test, the day's light cold test, the colour look, PR-5's identification test if not already run | LV2-0 | none | Results per protocol; each LD whose gate is human resolved by the user |
| LV2-1 Hierarchy and language | O-1, O-2, O-4, O-5, O-8, O-12/13/14, O-16, O-25 + **the context block (LE-2) + the e-stop two-step** | V2-U2 (or folded, LD-3) | **DR-1, DR-4, DR-5** (small) | Phone Now ≤ 2 screens with 4 approvals (**measured 1.0 in the lab**); 0 raw policy strings or ISO times at depth 1–2 (**measured 0**); every needs-you item decidable where shown |
| LV2-2 Phone-first | O-3, O-20, O-24, O-27 | V2-U4, P20 | per P20 | Physical-phone acceptance; Back never exits (**measured in emulation**); e-stop on every screen (**measured 6/6**) |
| LV2-3 Desktop composition and motion middle | O-6, O-11, O-15, O-18, **O-19 lean set only**, O-29 if LD-8 passes | V2-U2, V2-U3 | none | Qt p95 ≤ 16.7 ms per primitive; input ≤ 1 frame (**measured**); budget per item |
| LV2-4 Identity and causality in context | **O-9 as R3**, O-7 (after P21), O-21 after O-9's diary | P21, V2-U3 | **DR-6, DR-7** | Two-week diary |
| LV2-5 Relations re-scope | O-17 (+ LD-6), O-28 | V2-U5, P21 | none beyond P21 | 60 fps at the largest view; answers a recorded question |
| LV2-6 Senses (experiment) | O-22, O-23 | any | none | Opt-in; withdrawn if not kept |
| **Deferred, with a trigger** | count, tooltip group, release (+ spring), R1 as default | — | — | Re-open only if a human test asks for them |

## 14. Proposed production changes, and the decisions that need you

### 14.1 Proposed production changes (if, and only if, you approve the decisions below)

None of these is made. Each is listed with the decision that would authorise it.

| # | Change | Authorised by | Size |
|---|---|---|---|
| P-1 | The three places in the navigation table (relabel; World `phone: menu`) | LD-2, D-2 | Data edit |
| P-2 | Now rebuilt in the §4 order; one-line Decide rows; departure-board Running; Stopped with *because* | LD-2, LD-3 | CSS + markup |
| P-3 | The human-language layer on approvals, times, states and events; raw record at depth three | LD-9, LD-3 | 0.51 KB |
| P-4 | The context block and the row's context line, known/derived/unknown | D-1 | 1.43 KB (reducible) |
| P-5 | The phone: header e-stop, strip, three tabs, pushed decision and mission pages | LD-2, LD-5, LD-7 | 0.44 KB CSS + push 0.24 KB |
| P-6 | E-stop two-step in place of the modal | LD-7 | 0.32 KB |
| P-7 | Desktop composition C | LD-2 | 0.14 KB CSS |
| P-8 | Motion middle, lean set | LD-1, O-19 | 1.49 KB |
| P-9 | The day's light R3 | LD-4 | 1.72 KB (1.61 before the aligned axis) |
| P-10 | Data requirements DR-1, DR-4, DR-5 (each with its own Core/API design gate) | D-1 | small |
| P-11 | The design pass DP-1…DP-10 as the presentation of P-2, P-5, P-7 and P-9, with hex tokens added through `gen_ui` (not `color-mix()`) and a skip link in the router | D-5 | 1.30 KB gross, nets against V1 |

### 14.2 Decisions — the list

Flags: **P** prototype · **M** measurement · **H** human test · **A** architecture/API change ·
**R** production-ready · **✗** reject · **D** defer. A flag in bold is still owed.

| Id | Decision | What the evidence says | Flags | Recommendation |
|---|---|---|---|---|
| **LD-1** | V2 budget | Real committed ≈ 9.2 KB (not 9.7); the high-value half is ≈ free; the lean middle + R3 ≈ 3.1 KB; count/tooltip/release/R1 unjustified (`le6`) | P ✓ · M ✓ · A — | **≈ 12.5 KB visual behaviour + information layer under the V1 bundle gate.** Not 16–18 KB |
| **LD-2** | Three places + phone IA | Better on every question on every device on the proxy; phone 5.1 → 1.4 screens; e-stop 0/… → 6/6 (`le1`, `le4`) | P ✓ · M ✓ · **H** | **Accept as the LV2-1/LV2-2 target, conditional on the 5-second test and the thumb test** |
| **LD-3** | Fold O-1/O-2/O-4/O-8 into V2-U2 | They carry the measured gains and cost ≈ 0–2.4 KB; everything later draws on them | M ✓ · **H** | Fold (unchanged from LR) |
| **LD-4** | The day's light as a first-class surface | Possible from real data only (0 unsourced marks); R3 answers the question; R1 does not without hover (`le3`) | P ✓ · M ✓ · **H** · **A** (DR-7) | **Promote R3** to LV2-4 with the cold test and the diary as gates; R1 as an optional World view |
| **LD-5** | Phone decisions on a pushed page, not a sheet (amends A §M / §E.1's phone form) | The page holds the full decision context with a fixed 58 px bar; Back closes it; 1.75 screens for the longest decision (`le4`) | P ✓ · M ✓ · **H** | **Page** for decisions; sheets stay for quick reference. This **amends an accepted V2-U0 form** — your call |
| **LD-6** | Relations: user-scrubbed history; axis layout (amends VD §11 "then vs now, not replay") | Not prototyped: a scrubbable causal history needs P21's causality record; a lab built on invented causality would be the fabrication this project forbids | **A** (P21) · **P** · **D** | **Defer to LV2-5.** VD §11 stands until then |
| **LD-7** | E-stop: in-place two-step instead of a modal | Press arms for 3 s and says what the second press does; the second engages; no dialog; lapses safely; visible on every phone screen; forced-colours form distinct (`le4`) | P ✓ · M ✓ · **H** | **Two-step**, fixed in the phone header. Needs a hand check that "arm" is not mistaken for "stopped" |
| **LD-8** | Warm neutrals, state balance | Floors survive; warm at hue 70 sits 12° from the amber reserved for needs-you; light theme already balanced; dark failure colour is lighter-weighted than success (`le7`) | M ✓ · **H** | **No warm-at-70.** Show charcoal and the blocked-lightness lift to your eye; change nothing without V1's gates |
| **LD-9** | P2 "the honest record" + voice | 3 kinds of machine string → 0 at depth 1–2 for 0.51 KB; the honesty rule had to be applied to copy as well as light (`ld9`) | P ✓ · M ✓ · **H** | **Accept as the direction**, plus a rule: *every clause names the field it comes from* |
| **LD-10** | Sound experiment | Not built. Sound in QtWebEngine and in the PWA is unverified; no evidence in this phase for or against | **P** · **H** · **D** | **Defer to LV2-6** unchanged; off by default if ever run |

**Decisions this phase adds (not in LR):**

| Id | Decision | Recommendation |
|---|---|---|
| **D-1** | The four-kind context rule (known / derived / proposed / unknown) and the row's one context line (project · branch) | Accept as the rule for every context surface; DR-1, DR-4, DR-5 go to their own Core/API gates |
| **D-2** | Rename the desktop destinations (Work → Missions, Attention → Needs you) or keep V1's names on desktop and use the new ones only on the phone tabs | The lab used the new names everywhere; the 5-second test should include both |
| **D-3** | Count, tooltip group and release deferred until a human test asks for them | Defer |
| **D-4** | The budget method: price every V2 item as *marginal, minified, inside the V1 bundle* from now on | Accept; it is the number a user downloads |
| **D-5** | The design pass (`le8`): Apple HIG **principles** (not its glass), one leading edge, inset separators, list-header sections, tabular durations, quiet separators, non-breaking figures, capsule tab, floating strip on an opaque band, full-width Approve, aligned day's-light axis | **Accept as the presentation target for LV2-1/LV2-2, conditional on H-1…H-3**, which should run on the polished lab. Two trade-offs to judge by eye: the two-row phone decision bar (+60 px, Approve 2.6× wider) and the 28 px list-header spacing (+59 px on phone Missions) |

**Where this phase would change an accepted V2-U0 decision** (A stands until you say otherwise):
LD-5 (phone decision form, A §M/§E.1) and, only if approved later, LD-6 (VD §11). Nothing else
here contradicts A.

### 14.3 Human gates owed (none converted from a proxy)

*(completed below)*

### 14.3 Human gates owed (none converted from a proxy)

Each is ready to run on the lab as it stands; none has been run.

| Gate | For | Protocol | Pass |
|---|---|---|---|
| **H-1 5-second hierarchy test** | LD-2, LD-3, D-2 | A §V's protocol: show A, B, C Now (desktop 1,440 and phone) for 5 s each, order randomised, the user + ≥ 2 people unfamiliar with Archeus; ask the eight LE-1 questions from memory | B/C answers more of the eight correctly than A for every participant |
| **H-2 Decision comprehension** | LD-5, LD-9, O-2 | Show V1's approval card and the lab's decision page for the same plan; "what happens if you approve?", "why is it asking?", "what changed since last time?" | Correct and faster on the lab page for every participant |
| **H-3 Physical-phone thumb test** | LD-2, LD-5, LD-7 | The lab on an iPhone (Home Screen PWA) and an Android phone, one-handed: approve a decision, read why a mission stopped, stop everything, go Back from a decision | No mis-tap on Reject/Approve; e-stop in ≤ 2 presses from every screen; Back never leaves the app |
| **H-4 E-stop hand check** | LD-7 | 10 presses-to-arm with the first press only: does the armed state read as "not yet stopped"? Then 10 full stops | 0 cases of "armed" read as "stopped"; 0 accidental single-press stops |
| **H-5 Day's light cold test** | LD-4 | R1/R2/R3 shown cold: "what did Archeus touch today?"; then "would you look at this again tomorrow?" | R3 answered fastest and wanted again by the user |
| **H-6 Two-week diary** | LD-4 | LR §18's kill criterion | Used to answer a real question; else demoted to a World view |
| **H-7 Colour look** | LD-8 | Steel, charcoal and warm grounds beside the amber band and a blocked row, dark and light | The user prefers a variant **and** amber still reads first |
| **H-8 Motion feel** | O-19, D-3 | A day of use of the lean set in the Qt shell; note any motion that is noticed as motion | No primitive reported as slow or distracting; none asked for that is deferred |
