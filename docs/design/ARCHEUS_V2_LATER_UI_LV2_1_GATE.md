# Archeus later-V2 UI — LV2-1 gate: proof of the information architecture and presentation

**Status: APPROVED SCOPE (2026-10-05) · W0, W1, W3 (automated), W4 DONE · W2 HUMAN TESTS NOT RUN —
BLOCKED (§6).** No LD is accepted by anything in this document. Evidence and recommendation are
kept apart from decisions, and decisions apart from human validation and production
implementation: **LV2-1 changes no production file** — no V1, Core, API contract, `clients/app`
or V2 production code. Everything built is in `prototypes/v2-later/` and in five *draft* gate
documents under `docs/architecture/`.

Parent record: [ARCHEUS_V2_LATER_UI_EVIDENCE.md](ARCHEUS_V2_LATER_UI_EVIDENCE.md) (LV2-0, with its
§15 corrections log). Lab index: [prototypes/v2-later/README.md](../../prototypes/v2-later/README.md).

## 1. Decisions taken by the user at this gate (2026-10-05)

| Id | Decision | Effect in LV2-1 |
|---|---|---|
| Scope | LV2-1 = W0–W4; absorbs LV2-0b; later production phases renumbered (+1) | Evidence record §13 updated |
| **D-6 (a)** | A §F stays authoritative and the lab default; LE8's three typography values are a test arm only; PR-4's Qt clipping check re-run for that arm; §F not amended without a later explicit decision | `?type=le8`; §4.2 |
| **D-5** | LE8 tested as a presentation **candidate**, not accepted; two fixed rules decide its phone trade-offs | `?bar=one|two`, `?hdr=20|28`; §5.4 |
| **D-2** | Test V1 names and the new names; on a tie V1's names stay | `?names=v1|new`; §5.1 |
| **D-4** | All future V2 work priced minified, in-bundle | adopted |
| LD-1 | ≈ 12.5 KB of visual behaviour; keep measuring before adding visual weight | closed |
| LD-6 | Relations history scrubbing deferred until after P21 | closed (deferred) |
| LD-8 | The hue-70 warm grey is not used | closed |
| LD-10 | Sound deferred | closed (deferred) |
| D-3 | Number roll, tooltip grouping, phone drag-release deferred | closed (deferred) |

**Still open, and NOT accepted by this phase:** LD-2, LD-3, LD-4, LD-5, LD-7, LD-9, D-1, D-2, D-5.
LV2-1 must provide their human evidence first.

## 2. Scope

- **W0** — correct and instrument the lab (§3).
- **W1** — re-run the automated evidence on the corrected lab (§4).
- **W2** — run H-1, H-2, H-3 with the criteria fixed in §5 (**not run: §6**).
- **W3** — which context fields help identification (§7; the automated half done, the human half is
  H-1's context sub-test, not run).
- **W4** — draft the data-contract gates, implement none (§8).

## 3. W0 — the lab, corrected and instrumented

| # | Item | Where | Note |
|---|---|---|---|
| 1 | **§F typography is the default again** (phone verdict 30/36, −0.005 em, durations in Cascadia Mono) | `lab/base.css`, `lab/polish.css` | LV2-0 had set the phone verdict at LR's 24/30 without saying so (T-1) |
| 2 | LE8 typography as an arm: `?type=le8` | `lab/polish.css` | −0.012 em, phone verdict 24/30, durations in the text face |
| 3 | PR-4 Qt clipping re-run for the arm | `tools/pr4_le8.py` | §4.2 |
| 4 | Hard-coded policy rows **removed** (not sourced: O-13 is not under test) | `lab/ia.js` | T-2 |
| 5 | Switches `?names=v1|new` · `?bar=one|two` · `?hdr=20|28` · `?ctxrow=p|pb|prb|pbc` | `lab/ia.js`, `lab/polish.css`, `lab/ia.html` | defaults: names new, bar two, hdr 28 (the LE8 candidate), row context as LV2-0 (desktop pb, phone p) |
| 6 | Three look-alike days `?fx=1|2|3`: same states, counts, times, structure; different names, paths, branches, commits | `lab/fixture.js` (`lookalike`) | so a participant meets each variant without recognising it |
| 7 | Stress cases `?corpus=stress`: three missions with the same title in one two-repository project (one a submodule), a 104-character title in a 37-character project, Unicode (German, Japanese) in project, path and title | `lab/fixture.js` (`stress`) | |
| 8 | Moderator harness: counterbalanced plans, 5-s flash (`?flash=5`), timed tasks, wrong-path counting from the route log (desktop), answer keys computed from each day's fixture, H-2/H-3 forms, local JSON export only | `lab/harness.html`, `lab/harness.js` | `tools/harness_check.py` (§4.4) |
| 9 | Real phones: on-device press/route log (`?log=1`, `#lablog`, `#lablog-clear`), Home Screen app metadata, and a per-session server | `lab/ia.js`, `lab/ia.html`, `tools/serve_lan.py` | Android `--adb` (loopback + `adb reverse`); iPhone LAN mode for the session only (§6) |
| 10 | **Context made V1-true** (found by W4, checked by hand): repository = the repository at `Project.root_paths[0]`; "target branch" not recorded; V1-shaped worktree paths and task branches; the "output" link removed | `lab/ia.js`, `lab/fixture.js` | T-10, T-11, T-4 |

Scoring: `tools/h_score.py` applies §5 exactly, per participant; a miss is reported as a miss and
nothing is averaged. It reports **INCOMPLETE** (and no pass) below the participant mix in §5.0.

## 4. W1 — automated evidence on the corrected lab

### 4.1 IA probe, against LV2-0 and LE8

RESULTS_IA

### 4.2 PR-4 clipping check, LE8 typography arm (D-6)

PR-4's own lab and metric, loaded at the accepted `type=v2`, with LE8's three values injected
(`tools/pr4_le8.py` → `results/lv21/pr4-le8/`).

| Check | v2 (accepted §F) | LE8 arm |
|---|---|---|
| Clipped text elements, Chromium, 6 surfaces × 2 views × 8 environments (96 per arm) | 0 | **0** |
| Desktop layout facts (lead lines/height, first row, rows above the fold, scroll, truncated titles) | — | **identical to v2 in all 48 desktop combinations**: −1.2 % tracking changes no line at 1,440 px |
| Phone | lead 30 px | lead 24 px: −12 px per lead line on Now/quiet; dense lead 3 → 2 lines (−48 px, one more row above the fold); at 200 % −36 to −120 px |
| Qt 6.11 (real window), now / mission / dense, desktop and phone | (PR-4: Qt = Chromium) | **0 clipped**; desktop identical to PR-4's accepted Qt values; phone now and mission identical to Chromium; **phone dense differs: 3 lead lines in Qt vs 2 in Chromium** — Qt's classic 15 px scrollbar narrows a 390 px window (recorded by PR-4 for the dense lead box), not the arm |

**Result: the LE8 typography arm passes PR-4's clipping check.** That makes it *safe to test*;
it does not make it better, and §F stays the default (D-6 (a)). Its one measured effect is phone
height; whether that is worth amending §F is a separate decision (§9).

### 4.3 Day's light, mutation gates, render count

- Day's light (`results/lv21/light.json`, the LE-3 probe re-run on the corrected lab): RESULTS_LIGHT
- Lab gates (`results/lv21/mutate_gates.txt`): **6 of 6 killed** (provenance ×2, machine language ×2,
  duplicate decision, the contrast case axe misses).
- **The 54/56 discrepancy is reconciled (T-8):** the probe has always produced **56** renders —
  2 devices × (4 forms × 3 days in dark + 4 forms × 4 other environments) — in both the LV2-0
  (3,264 drawn elements) and LE8 files. "54" was a transcription error in the records.

### 4.4 Harness, scorer and phone server checks (`tools/harness_check.py`)

**0 failures.** The scorer reports exactly the planted misses, per participant, with no
averaging. It covers: an invented remote, which also fails 9/9; 4/6 phone recall, which also fails
B ≥ A; armed-described-as-stopped; a 61 s task. It also calls 4 participants INCOMPLETE, keeps the
smallest always-right row context, and keeps V1's names on a tie. Counterbalancing holds for
plans 1–8. All 17 keyed trials of a full plan open and fill their keys with no page error. The
phone server refuses:
- no token, a wrong or forged token, and a rebound Host;
- POST, directory listings, and anything outside the two roots.

It sets an HttpOnly SameSite=Strict cookie.

## 5. The human protocols — FIXED 2026-10-05, before any participant

These are the user's criteria verbatim. They may not be changed after the first participant
session.

### 5.0 Participants and conduct

The owner plus **≥ 4** others; **≥ 2** who have never used Archeus; **≥ 1** who uses a coding
agent daily. No recording unless the participant explicitly agrees. One fixed moderator script
(the harness shows each task's exact words); counterbalanced order (§5.5). If the additional
participants cannot be arranged, **stop before the human gate and report the blocker** rather
than weaken the criteria.

### 5.1 H-1 — recognition and findability

Desktop 1,440 px and phone 390 px. A = V1-structure replica, B = three places, C = wide desktop;
all with the LE8 presentation as an experimental arm (§F typography, D-6 (a)).

**Recall** (after 5 s): 1 Name one running mission · 2 How many items need you? · 3 Is anything
stopped? · 4 Which project is the running mission in? · 5 Was anything verified today? · 6 What
would you do first?
*Pass:* B ≥ 5/6 for every participant on desktop; B ≥ 5/6 for every participant on phone; B ≥ A
for every participant.

**Findability** (from Now): 1 What is happening now? · 2 What needs you? · 3 Find mission X ·
4 Which project is Y in? · 5 Which branch and repository is Y on? · 6 What changed since you last
looked? · 7 Which checks passed for Z? · 8 What happened today? · 9 Which remote is Y on? (correct:
**"not recorded"**).
*Pass:* 9/9 for every participant; each task < 60 s; median ≤ 10 s desktop, ≤ 15 s phone; ≤ 2
wrong-path taps per participant; B's median beats A on ≥ 7/9 tasks; project and branch correct for
every participant; zero invented remotes.
*Naming rule:* the naming variant that reduces task errors or median time by ≥ 10 % is chosen;
otherwise V1's naming is retained.
*Context rule:* rows carry the smallest context field set that achieves 100 % correctness when
distinguishing similar missions by repository and branch; every additional field must
demonstrate measurable benefit.

### 5.2 H-2 — decision comprehension

Desktop approval pane and phone decision page against V1's approval card. 1 What happens if you
approve? · 2 Why is it asking? · 3 What changed since the last version? · 4 When does it expire? ·
5 Which project and branch? · 6 What was verified? · 7 Where will it deploy? (correct: **"not
recorded"** where appropriate).
*Pass:* ≥ 6/7 correct for every participant; new page ≥ V1 card for every participant; median
correct-answer time for #1 ≤ 15 s; zero invented facts.

### 5.3 H-3 — physical phone, one-handed, standing (H-4 folded in)

iPhone Home Screen app; Android Chrome; dark and light; 360 px / 200 % text.
Tasks: 1 identify the running mission · 2 identify what needs attention · 3 from the strip, name
the current step and project · 4 stop everything from a moderator-selected screen · 5 Back from a
decision page · 6 Back from a mission page · 7 repeat the key tasks at 360 px / 200 %.
*Pass:* zero Approve/Reject mis-taps; zero cases where "armed" is described as "stopped"; zero
full stops from one press; full stop in ≤ 2 presses / ≤ 5 s; Back never exits the application;
because/cause answer correct within 20 s; project visible from the strip within one tap; no
sideways scrolling at 360 px / 200 %.

**Reconciliation item R-1 (for the user to confirm before the first participant, no criterion
changed):** two H-3 criteria refer to tasks the H-3 task list does not name — *Approve/Reject
mis-taps* needs an approval task, and *because answer within 20 s* needs a "why did it stop?" task.
The harness therefore adds **ap1/ap2** (approve a named decision, once per decision-bar arm — this
is also what D-5 rule 1 is measured on) and **why**. Nothing is weakened; if you would rather drop
those two criteria instead, say so before the first session.

**R-1 resolved (user, 2026-10-05): both criteria kept, thresholds unchanged.** The two tasks were
already in the harness; this is the mapping, not a new criterion:

| Fixed criterion (verbatim) | H-3 task (exact words the harness shows) | Recorded as | Scored by `h_score.py` |
|---|---|---|---|
| zero Approve/Reject mis-taps | **ap1** "Approve “the plan for the deploy” (bar arm 1)." on `#d/m-91d2`; **ap2** "Approve “the plan for the upgrade” (bar arm 2)." on `#d/m-2b7f` | per task: `ok`, `mistap`, `hesitate` (> 2 s), time; device log as the press record | `H3 zero Approve/Reject mis-taps` — **NOT RUN unless both ap1 and ap2 are recorded**; the same marks feed D-5 rule 1 |
| because/cause answer correct within 20 s | **why** "Why did the migration mission stop?" (the BLOCKED mission, Z) | `ok`, time | `H3 because correct within 20 s` = correct **and** ≤ 20 s; NOT RUN without a time |

The moderator's key for both (and for t3) is computed from the device's own fixture day: ap1/ap2
show the decision's title, *why* shows Z's recorded `because` chain (two hops, both from the
Verification record — e.g. "Verification failed at 13:48 → check “rollback” failed (exit 1): …").
t7 repeats *why* at 360 px / 200 % under its own "all three correct" mark; it does not count toward
the 20-s criterion, which is measured on *why* alone.

### 5.4 The two LE8 rules (D-5)

1. The two-row phone decision bar survives only if its mis-taps and > 2 s hesitations are no worse
   than the one-row bar's **and** time-to-approve is not worse (measured on H-3 ap1/ap2, each
   participant meeting both bars in counterbalanced order).
2. The extra list-header spacing (28 px) survives only if it gives a measurable benefit under the
   agreed criteria — scored as the ≥ 10 % rule on H-1 task 3 ("Find mission X", the Missions page),
   desktop and phone, between participants (header arm alternates 28, 28, 20, 20 by order index,
   decorrelated from the naming arm); otherwise the compact 20 px returns.

### 5.5 Counterbalancing (`harness.js` `plan(n)`)

Desktop recall: A, B, C rotated by participant, each on a different look-alike day. Phone recall:
A, B rotated. Findability: A and B on different days on each device, order rotated. Context arms
p, pb, prb, pbc rotated (stress corpus). H-2: the four pages rotated. H-3: iPhone dark, Android
light; bar arms in alternating order.

**Known limits, stated before running:** three look-alike days cannot give every one of a
participant's eleven screen trials a fresh day, so a day recurs across devices (never within a
device's A/B pair). The four context arms all use the stress corpus, so a participant may learn
which look-alike is which; the context result therefore counts the **first** arm separately
as well as all four. Phone wrong-path taps are counted by the moderator (with the device log as
the record); desktop ones from the route log.

## 6. W2 — human tests: NOT RUN (blocker)

### 6.0 Readiness check (2026-10-05, before any participant; no participant run, no evidence claimed)

`py prototypes/v2-later/tools/harness_check.py` → **FAILURES: none** (the scorer self-test uses
synthetic session files in a temp directory; `results/lv21/sessions/` is empty and `human.json`
reads INCOMPLETE with n = 0). Synthetic sessions test the scorer; they are not participants.

| Item | Result |
|---|---|
| Harness | every desktop stimulus opens with no page error; every trial's answer key fills (17); both H-3 trials fill t3/ap1/ap2/why keys |
| Randomisation / counterbalancing | plans 1–8: desktop recall A/B/C on three different days, each variant leads once in 1–3; findability A/B on different days per device; four context arms; names alternate; header 28, 28, 20, 20; bar order alternates |
| Synthetic fixtures | look-alike days 1–3 and the stress corpus load and key correctly; honesty probe over 180 loads (days 1–3 × busy/stress × A/B/C × five routes × 1,440/390): **no remote, no owner/repo, no "Into main"** on any page; mission pages in B/C say *Not recorded by Core: remote* |
| Phone serving / security | per-run token in the path → HttpOnly SameSite=Strict cookie; no/wrong/forged token 403; rebound Host 403; POST 405; no listing; nothing outside the two read-only roots; private-address refusal; 45-min self-stop |
| Results per participant | localStorage keyed by participant code; export `lv21-<code>.json`; scored and reported per participant. Codes must be unique (re-using one overwrites) |
| Missing criteria cannot be averaged away | **fixed here, see below**; mutation-verified |
| Moderator script fixed | task words are constants in `harness.js` (`RECALL`, `FIND`, `DECIDE`, `H3`); the plan banner tells the moderator to read verbatim, give no hints, not confirm answers |

**Defects found by the readiness check and fixed before any participant (prototype tooling only;
no task wording, criterion or threshold changed):**

1. `h_score.py` scored an **unrecorded** H-3 task as a **pass**: no ap1/ap2 marks read as "zero
   mis-taps", an empty t4 as "never armed-as-stopped" and "no one-press stop", an empty t7 as "no
   sideways scrolling", and no findability trials as "zero invented remotes". Each is now NOT RUN.
   Back / because / strip, unrecorded, now read NOT RUN instead of a miss.
2. `COMPLETE` checked only the participant mix. It now also requires **every criterion run for
   every participant** and every group rule computable (`not_run` lists the gaps). Mutation:
   reverting either fix fails `harness_check.py`.
3. `h_score.py` printed nothing (`return` before the report); the per-participant miss / not-run
   listing now prints.
4. The H-3 checklist showed the moderator **no answer key** for t3, ap1, ap2 or *why*, so "because
   correct" would have been judged from memory against a fixture day whose names differ. Keys added
   (§5.3, R-1 table).
5. The harness's phone-URL placeholder described a `k=` parameter the server no longer uses.

**Participant count — flagged, not changed:** the request for this step said "at least 4
participants"; §5.0 as recorded says **the owner plus ≥ 4 others**. The scorer enforces §5.0
(5 sessions including the owner). Lowering it is your call, before the first session.

**Environment blockers, checked 2026-10-05:** no participants are reachable from this session; no
phone is attached; **`adb` is not installed** (not on PATH, no `%LOCALAPPDATA%\Android\Sdk`), and
`winget` is not available to install it.

**W2 progress (2026-10-05): 1 session run, W2 paused** by the user for time; its file was not yet
exported when the servers were stopped. One session decides nothing (§5.0); LV2-1 stays open.

**Android H-3 deferred, not dropped (user, 2026-10-05):** no Android phone is available, so each
participant's `h3-android` trial is left unfinished and run later as a make-up session, same
participant code, same harness origin (`127.0.0.1:8765`, same browser profile). §5.3 is unchanged.
Until every make-up is done, `h_score.py` stays **INCOMPLETE** (`H3 run (android)` is NOT RUN),
and so do the parts that rest on it: H-3's light-theme coverage (the iPhone arm is dark) and half
of D-5 rule 1's ap1/ap2 data. LD-5, LD-7 and D-5 cannot be decided before then.

### 6.1 What is ready

The tests need four people besides the owner, at least two of them new to Archeus, plus an iPhone
and an Android phone in hand. None of that is reachable from this environment. **No participant
has been run and no human criterion has been evaluated.** Per §5.0, the phase stops here rather
than weaken the criteria. What is ready:

1. `harness.html` on loopback: `py prototypes/v2-later/tools/serve_lan.py --adb` serves it locally too, or
   any `serve.py` page. Open `harness.html`, enter the participant code and order index, build the
   plan, and read each task exactly as shown.
2. **Android:** install Android platform-tools (adb is not installed on this machine), connect the
   phone with USB debugging, run `serve_lan.py --adb`, then `adb reverse tcp:PORT tcp:PORT`, then
   open the printed URL on the phone.
3. **iPhone:** `serve_lan.py` (LAN mode) for the session only; allow the firewall prompt for
   **private** networks only; open the printed URL in Safari, Add to Home Screen, open from the
   icon; stop the server when the session ends (it also stops itself after 45 minutes). The token
   is new each run.
4. Export each participant's JSON into `prototypes/v2-later/results/lv21/sessions/`, then run
   `py prototypes/v2-later/tools/h_score.py`.

## 7. W3 — context study (automated half)

**What V1 can actually show, per field** (the lab renders only known or derived facts; unknown
facts are left off the row and named once in the context block):

| Field | Kind in V1 | On a row | Note |
|---|---|---|---|
| Project | known (`Project.name` via `Mission.project_id`; DR-1 is only the read join) | every mission with a project | — |
| Branch | known (`Mission.integration_branch`) | 6 of 10 busy-day rows, 11 of 15 stress rows | missions that never executed have none, so it is **left off**, not shown as a placeholder |
| Repository | derived: the repository at `Project.root_paths[0]` (T-11) | every row | **the same for every mission in a project**, so it never separates missions within a project. It is also named by its **folder**, which need not match the project: the archeus project's repository reads "Claude" |
| Commit | known (`Mission.integration_head`) | 6 of 10 / 11 of 15 | not a recognition aid; read once on the mission page |
| Remote | **unknown** (DR-2) | never | the block says "Not recorded by Core: remote" |
| Operation inside a task | **unknown** (DR-6, P21) | never | the task and step N of M are known and shown |
| Environment | **unknown on plan approvals** (T-13; DR-4) | never | "includes a deploy" is the recorded fact |
| Verification | known | on Review/Stopped rows as words; checks on the page | DR-8 for the output itself |

**Cost and separability per row arm** (`tools/density_probe.py` → `results/lv21/density.json`; Missions page; each cell is *mean row height Δ · page height Δ at 100 % / the same at 200 %*, against `p`):

| Arm | Desktop 1,440 | Phone 390 | Small 360 | Overflow | Separates the three look-alikes from the row |
|---|---|---|---|---|---|
| `p` project | — | — | — | 0 | rows differ (step, time) but **no row says which branch** |
| `pb` + branch | +1 px · page +11 / +4 px · +56 | +5 px · +78 / +28 px · +417 | +4 px · +65 / +30 px · +449 | 0 | **yes, by branch, on every row** |
| `prb` + repository | +2 px · +31 / +15 px · +226 | +8 px · +118 / +45 px · +679 | +6 px · +88 / +65 px · +970 | **1 row at 200 % on 390 and 360** | by branch only — the repository is identical for all three |
| `pbc` + commit | +1 px · +11 / +12 px · +184 | +6 px · +96 / +33 px · +490 | +6 px · +84 / +47 px · +706 | 0 | by branch (the commit adds nothing a person reads) |

(stress corpus, 15 missions; the busy day shows the same order at smaller sizes.)

**Automated ranking (a structural proxy, not the human result):** **1. project · branch (`pb`)** —
the cheapest arm that separates same-titled missions, and the only extra field that does; **2.
project only (`p`)** — cheapest, but cannot answer "which branch" from a row; **3. `pbc`** — cost
without separation; **4. `prb`** — the most cost, overflows at 200 % on both phones, and in V1 the
repository cannot separate missions within a project at all. Repository, commit, remote,
operation and environment belong one level down (the context block), where they are shown with
their kind. **The human context rule (§5.1) decides; this only predicts it.**

## 8. W4 — data-contract gates (drafted, not implemented)

| Gate | Requirement | What the drafting found | Open decisions |
|---|---|---|---|
| [DR-1](../architecture/lv2-dr1-project-name-gate.md) | Project name on mission, attention and digest reads | The client can already join `/v1/projects`; duplicate project names are legal | Client join (recommended) or a Core read field; current name vs name at the time; telling duplicates apart |
| [DR-2](../architecture/lv2-dr2-remote-url-gate.md) | `Repository.remote_url`, provider and owner/repo **derived**, credentials **stripped** | No inspection reads remotes today (T-12) | Record at inspection (recommended) vs live; ssh normalisation; which remote; local-path remotes on a paired phone |
| [DR-3](../architecture/lv2-dr3-mission-repository-gate.md) | Which repository a mission works in | Core runs every execution at `root_paths[0]`; a submodule can never be a mission's repository (T-11); `default_branch` is never written (T-10) | A recorded `Mission.repository_id` or the documented rule (recommended for now); record `default_branch`; a root that spans several repositories |
| [DR-4](../architecture/lv2-dr4-approval-environment-gate.md) | Environment, branch and host on approval records | Already kept in `Approval.items`, dropped only by `presented.what`; plan approvals carry none; only `prod` is detected (T-13) | Part 1 only, Part 1 + plan-time environment (Part 2), or the client reads `items` |
| [DR-8](../architecture/lv2-dr8-verification-output-gate.md) | Read-only check output | Stored **unredacted in two places** — the artifact (last 256 KiB) and the **complete** output as a plain log under the run directory (`evidence.py:69-79`, `node/local.py:428-462`) — and served by no route (T-4) | **Security, with P20:** who may read (recommended: local credentials only, wider redaction); at-rest redaction to P20's secrets review; size cap (16 KiB default, 64 KiB ceiling); audit of remote reads |

DR-5 stays a V1 defect (V1's own follow-up). DR-6 belongs to P21. DR-7 belongs to the day's-light
phase.

## 9. Remaining decisions

REMAINING

## 10. Recommended next phase

NEXT
