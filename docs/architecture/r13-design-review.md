# R13 — Independent design review of P19 (P19.5's exit review)

Status: **PASSED after the correction pass (§9).** Both blocking findings (R13-01, R13-02) are
resolved in the implementation and re-checked. The manual checks of §6 and the user's sign-off
are still outstanding, and P19.5 does not exit without them.

Status as first recorded (commit `0558d3a`, unchanged below): **REQUIRES A CORRECTION PASS.**
Two findings block exit (§3, R13-01 and R13-02). The rest are corrections that do not block,
decisions for the user, or wording changes to the documents. Nothing in the implementation was
changed by this review.

Date 2026-10-04. Branch `archeus-v1-rearchitecture` at `c744763`, which is P19 B1–B12. Nothing
is pushed.

Authority, in this order: the rulebook
([../design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md](../design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md),
including §46.1–§46.3), the P19 gate ([p19-design-gate.md](p19-design-gate.md), §4.1's decisions
and the deviations in §12), the design system, ADR-0026, ADR-0027, ADR-0042 and ADR-0044, and
execution-architecture §10. R13 is the rulebook's §36 step: "independent adversarial design
review against this rulebook". Its rubric is §37: problem → impact → fix, severities P1/P2/P3,
and the template test in §33. This review adds no requirement that these documents do not
already contain.

## 1. Method and evidence

The review did not rely on the implementing sessions' accounts. Each area was read from source
and then seen running.

- **Source read.** These files were read in full or in the parts that matter here:
  `Mission.tsx`, `Now.tsx`, `Relations.tsx`, `ui.tsx` (ActionButton), `state/now.ts` and
  `data/snapshot.ts`. Also the CSS for the inspector, the thread line, `.view` and `.main`.
  On the shell side, `gui_qt.py` `run_v1` and `archeus/cli/gui.py`, plus `main.estop`. On the
  TUI side, the Attention card in `screens.py`. The token and navigation tables were read too.
- **Run.** Three scratch scripts ran outside the repository, with their own `ARCHEUS_HOME`
  and nothing written to the tree. They drove a real Core (the e2e `TempCore`) and the built
  SPA in Playwright Chromium, plus the TUI's `App` frame:
  - one mission EXECUTING and one waiting for plan approval;
  - `status`, `why` and `stop` said in the running mission's thread;
  - `emergency stop` said in primary, and `approve` said in the waiting mission's thread.

  Each page was captured, and its `innerText` read, at 1440×900 dark, light and light + high
  contrast, and at 390×844 touch. The offline cold start was captured on the phone context.
  Measurements taken:
  - computed focus outline;
  - target sizes;
  - `scrollWidth`;
  - the confirm dialog's default focus;
  - the `data-theme` and `data-contrast` attributes after each choice;
  - ΔE (CIE76) between the tray icon's pixels and `state-attention`.
- **Not run.** No mutation or full-suite rerun. Those baselines are the ones the brief states
  (§8): 2565 passed, 1 failed, 13 skipped, 5 xfailed, and 137/137 mutants killed.

No console error was seen on either page.

## 2. Requirements reviewed

| Area | Governing requirement | Verdict |
|---|---|---|
| Mission Now tab (S1) | B3 (a) / §4.1; A-05 surfaces; §46.2 | conforms as decided (observation R13-14) |
| Mission conversation, cards, status | B5, B10, ADR-0042 §1–§3; principle 13; §15 actions | conforms, with copy findings R13-05 to R13-08 |
| Approve / start / review | B5, B6; §15, §17, App. B (Reject approval and Reject review confirmed, Cancel default) | conforms: the chat Reject confirms with Cancel focused (measured); wording R13-07 |
| Relations list (B1) + T2 (B2) | §11, ADR-0026 §1, B2 | conforms (decision request R13-11) |
| TUI T2 marker | design system TUI row; §12 item 1 | built `│`, a recorded deviation (R13-16) |
| Pause all in the tray | DS §13, X-24, B8 | conforms |
| Emergency stop | §6 O-1 "behind confirm"; §17 "destructive confirm: modal dialog, Cancel default"; execution-arch §10 | **does not conform in the tray (R13-01)**; strip, Control and chat conform |
| Attention and arrival | §17, §42, A-08; principle 13 | A-08 not re-measured (tests); copy R13-04 |
| Resource directives / change card | ADR-0042 §3, B10 items 37–45 | conforms (R13-09, R13-12) |
| Plan editing (B4) | B4, §4.1; §20 floors; WCAG 2.5.7 (no drag) | conforms: Move up and Move down buttons, 44 px targets on the phone (measured); R13-10 |
| Appearance (B9) | ADR-0044 §1–§4, T1–T6 | conforms: Light and High applied (measured); the doc conflict is R13-15 |
| Offline snapshot (B7) | B7 / §4.1, §12 items 70–75; §42 offline cells; §9; principle 13 | **does not conform in substance (R13-02)** |
| Persistent profile, pre-load bg | ADR-0044 T5, B8 | conforms by code and the offscreen test; manual check pending |
| Cross-device / unification | B12, G3 | conforms by `test_unification.py`; a real phone is pending |
| TUI parity | §46 TUI row, P17 | conforms for P19 additions; pre-existing copy R13-04 |
| Desktop shell / tray | B8, DS §3.2 :103, §8 | conforms except R13-01; doc conflict R13-15 |
| Responsive / mobile | §19, §20 floors | conforms: no sideways scroll at 390 px, every P19 control 44 px high (measured); R13-02's gutter is the exception |
| Focus ≠ attention | ADR-0028, §23 | conforms: the focus outline measured `rgb(244,241,234)` 2 px solid (thread ink) |

## 3. Findings

Severity follows §37's rubric. **P1** is unsafe, or breaks an approved rule on a P19 surface.
**P2** impairs the surface's purpose or breaks a rulebook rule. **P3** is polish, a document,
or a decision request. "Blocks P19 exit" means it must be corrected before R13 can pass.

### R13-01 — The tray's Emergency stop has no confirmation · P1 · **blocks**

- **Requirement.** Rulebook §6 O-1: "Emergency stop behind confirm". §17: "destructive confirm
  — modal dialog, Cancel default". Pause all and the e-stop share the tray through X-24.
- **Built.** `claude_sessions/gui_qt.py:236-242`: the tray menu's `Emergency stop` action calls
  `shell.estop()` directly. That runs `main.estop()` (`archeus/cli/main.py:325`):
  `POST /v1/estop`, which kills every running execution and disarms Core until a device
  re-arms it. `tests/v1/e2e/test_gui_qt.py:93,154` asserts the trigger reaches `estop`
  immediately.
- **Conforms?** No. Every other e-stop entry point confirms first:
  - the strip (`App.tsx:587`) and Control (`Control.tsx:866`), each with a modal whose Cancel
    has default focus;
  - the conversation (`Now.tsx:485`), where the card is the second step after the words.

  The tray is the only place where one click does it, and its item sits directly under Pause
  all.
- **Impact.** A misclick in a context menu kills all running work and disarms Core.
- **Correction.** Ask before running it: a native confirmation with Cancel as the default and
  the strip's own sentence. Then update `test_gui_qt.py` to assert the confirmation, and add a
  mutant that skips it. Item 83 (Core down) is unaffected.

### R13-02 — The offline snapshot cannot say what needs you, and the view has no margin · P2 · **blocks**

- **Requirement.** B7 / §4.1: "the Now composition … shown read-only" on a cold start. §9
  lists what Now "must show without navigating": needs you and since you last looked.
  Principle 13. §19 includes safe areas in what survives on mobile.
- **Built.** All three defects show in the 390 px offline capture:
  1. **The mission that needs you is dropped.** `keptData` (`data/snapshot.ts:27`) keeps only
     `activeMissions`, and `SETTLED` (`generated.ts:6`) includes `APPROVAL_REQUIRED`,
     `PAUSED` and `BLOCKED`. So the mission waiting for approval is not kept. Offline "Needs
     you" reads only "◆ Pending Approval", with nothing saying what for, and that mission
     appears nowhere else in the view. Online, the same block reads "Approve this plan version
     for *Deploy the release notes* · plan v1".
  2. **Since you last looked has no names.** `OfflineNow` (`Now.tsx:214-222`) prints
     `ref.kind`, so 20 rows read "mission · needs you · 9 events", "message · progressed · 1
     event", and so on.
  3. **No page margin.** `OfflineNow` is rendered outside the shell (`App.tsx:64`), and
     `.view` (`app.css:492`) has no padding (the gutter is `.main`'s). On a phone the text
     runs to x = 0.
- **Conforms?** In form, yes: a banner, "as of", read-only, no command. In substance, no: the
  snapshot cannot answer the one question it exists for.
- **Impact.** What a user most needs from it, what is waiting on them, is unreadable offline.
  The real-phone cold-start check of §10 would fail as soon as anyone looked at it.
- **Correction.** All of it is client-only and inside B7's own reads:
  - keep every non-terminal mission, or keep the titles of the missions Attention names;
  - name Needs-you and digest rows from the kept data, falling back to the kind;
  - give the offline view the shell's gutter.

  Extend `test_spa_offline_snapshot.py` to assert the waiting mission's title and the side
  padding, with mutants. If the user does not want the extra titles at rest (B7's security
  note), the alternative is to name the attention item from its own `reason` and say plainly
  that the title is not kept.

### R13-03 — "Since you last looked" is flooded with message rows · P2 · decision before P19.5 exit; does not block P19

- **Requirement.** §9: since you last looked is visible without navigating, and its rows
  stopped showing raw ids. §7.1: hierarchy. Principle 13. §33 weakness 8.
- **Built.** Core's digest (`archeus/core/world/digest.py`, unchanged since P12) names every
  entity, conversation messages included. P19 multiplies messages: B5's approval card on every
  approval, every turn and reply in a mission's thread, and B10's cards. In the capture, 12 of
  the 20 digest rows are "message progressed · 1 event", with no name, on desktop and phone
  alike. The TUI prints them as `message msg_01M43MWQ…`, which is a raw id. The offline view
  inherits them too (R13-02).
- **Impact.** The changes that matter (a mission waiting, a policy decision) are buried among
  rows that name nothing a person controls.
- **Correction.** This is the user's decision, because the mechanism is Core's and predates
  P19. There are two options:
  - **(a)** the digest stops naming `message` rows: a message is shown by the conversation,
    and its effect by the objects it links;
  - **(b)** the clients fold messages into one "N new messages" row that links the
    conversation.

  Either one also removes the TUI's raw ids.

### R13-04 — Approval cards show policy-rule ids, an ISO timestamp and (in the TUI) a Python list · P2 · does not block P19

- **Requirement.** Principle 13. §15: "ids, hashes and JSON move behind a Details disclosure".
  §42 Attention: "what, why, action, what next". §29's copy and id gate.
- **Built.** This is code from before P19, but it sits on the P19 Now and Attention surfaces.
  - **The SPA Attention card** (Now's Needs you block and Attention):
    - "Why it asks" prints `profile:standard@2:USER:deploy (ASK, USER); builtin:floor:deploy-prod (ASK, GLOBAL, locked)`;
    - "Expires" prints `2026-10-05T14:25:32.819Z`;
    - "Covers" prints `plan-lifetime`;
    - "Target" prints `task: work`;
    - the "Class" header wraps to "Clas / s" at 1440 px.
  - **The TUI card** (`archeus/cli/tui/screens.py:671-676`):
    - "Why it asks" prints `['ASK deploy: …']`, the Python repr of a list (`p['why']` is a
      list; `T()` stringifies it);
    - "Action hash 726f61785ecf9573…" sits in the primary card, where the SPA puts it under
      Details.
- **Impact.** The safety-critical card is the one that speaks least plainly. The TUI shows a
  rendering bug.
- **Correction.**
  - Join the TUI's list as the SPA's `Prose` does, and move its hash under a details line.
  - Render the rule ids as their profile and floor names in words.
  - Print the expiry as a local time.
  - Stop the class column wrapping.

  The copy gate missed these. Extend it to match `@\d+:` and ISO timestamps.

### R13-05 — A bare `why` in a mission's thread goes to the brain, and the answer contradicts itself · P3 · decision request

- **Built.** §12 item 14 deliberately keeps `why` with an explicit object, so bare `why` in
  the thread of an EXECUTING mission reaches the brain. With no permitted harness, the reply
  is: "I could not read this message: no harness is permitted … (provider terms, ADR-0021:
  `archeus terms <harness> permit`). Please rephrase it, or use a control verb (pause, resume,
  status, why, remember)." So the reply names `why` as the verb to use, just after refusing
  it. It also cites an ADR number in the user's conversation (principle 13). That reply text
  predates P19 (`conversation.py:357`).
- **Request.** Should bare `why` (and `status`, R13-06) in a thread be about the thread's
  mission, as `pause`, `resume` and `stop` already are? Separately from that decision, take the
  ADR reference out of the user-facing text.

### R13-06 — `status` replies in raw state enums · P3

`status` (`conversation.py:852-856`) answers "Ship the date-parser fix (EXECUTING); Deploy the
release notes (APPROVAL_REQUIRED)", and in a mission's thread it reports the whole workspace
(item 14). The rest of the app says these states in words, through `presentation.json`. Use the
same words here.

### R13-07 — Chat-card wording · P3

- `This approval is approved.` (`Now.tsx:463`, `Attention.tsx:129`) reads badly. The state is
  already a word on the card.
- The stop card prints the state twice, once as a raw lower-cased enum and once as the badge:
  "This mission is executing. ● Executing" (`Now.tsx:513`). A raw enum such as
  `approval_required` can appear there.
- The chat **Reject** confirm says "Reject what this approval asks. A decided approval cannot
  be changed." It does not say what Attention's card says, that rejecting cancels the mission.
  Its confirm button is styled `primary`, while Attention's Reject is `danger`. The confirmation
  itself conforms (App. B: Cancel is focused, measured). Only the consequence and the styling
  are inconsistent.

### R13-08 — Two live approval cards for one approval in a thread · P3 · accept or decide

After a bare `approve`, the thread shows the original card (linked from primary) and the
reply's card (item 17), each with Approve and Reject (capture `d10`, desktop and phone). That is
harmless, because Core decides once, but redundant. Item 17 recorded it, so accept as built
unless the user prefers the reply to link the existing card instead.

### R13-09 — A standing change card never closes · P3

`ChatChange` (`Now.tsx:545-566`) closes a mission-scope card once `since` moves. A
standing-scope card keeps "Save policy" live after it has been applied. That is harmless,
because the command is idempotent per key, but a second press re-sends it. Closing it when the
account's consumption already equals the proposal would match the mission case.

### R13-10 — The plan editor's Kind lists raw enums · P3

The options are `TASK_KINDS` values (`code_change`, `research`, `doc`; `Mission.tsx:375-380`),
and the task row tags them the same way. Principle 13 asks for words. One small presentation
map fixes it.

### R13-11 — Relations rows print the source column · P3 · decision request (P16 vs rulebook)

Every row ends with its field (`Mission.context_package_id`, `executions.mission_id`,
`plans.mission_id`; `Relations.tsx:78`), visible at both widths. That is P16 §20.5's
requirement ("each row says which field it was read from"), and it predates P19. It conflicts
with the later rulebook's principle 13 and §15 ("raw data behind Details"). The two approved
documents disagree, so the user should decide: keep it visible, move it into the row's
accessible description or tooltip only, or move it behind Details.

### R13-12 — One command, two names across clients · P3 · decision request

`setMissionResources` is "Save preferences" in the SPA (`Mission.tsx:258`, `Now.tsx:557`) and
"Set routing preferences" in the TUI (`screens.py:366,1121`). The SPA also uses "Set routing
preferences…" as its form opener. `test_one_name_per_command` reads only the SPA. §12 item 43
records this. The decision is whether "one name per command" (§40.5) applies across clients.

### R13-13 — PLANNING and APPROVED missions appear twice on Now · P3 · P19.5 (R8), not P19

Happening now uses `activeMissions`, which is every non-`SETTLED` state, so it includes
PLANNING and APPROVED. Upcoming (`state/now.ts`) lists those same missions again. The offline
view mirrors this. §9 gives them to Upcoming. Exclude Upcoming's states from Happening now.

### R13-14 — The mission Now tab puts the conversation above active work · P3 · observation, decided

B3 (a), the user's choice, puts the thread above the executions. As item 15 records, on a short
window the attempt's row falls below the fold, so A-05's line is not drawn. That inverts §7.1's
order (active work above history) at mission scope. **It is accepted as decided.** The note is
here only so a later reversal can cite it.

### R13-15 — Document drift that needs the user's amendment · P3

None of these changes behaviour. The rulebook is amended only by the user (its header).

1. **Rulebook §23** says "following the OS; no app switch". ADR-0044 (D-21) supersedes the
   design system §3.3 and plan B.3, but §23 is not marked superseded.
2. **The TUI's changed marker.** Rulebook §29's P17 row ("`›` changed (BUILT)") and §46's TUI
   row ("`›` changed") disagree with what was built, `│` (§12 item 1). The P17 row was also
   never true: §1.2 records that the TUI had no T2 before P19.
3. **The tray icon's colours.** Design system §3.2 says "`attention` is the only colour allowed
   to appear in … the tray icon". The tray uses the approved app icon (rulebook §8: the tile
   mark, gold artwork on dark), so gold is always present. That is the right icon by §8.
   Measured, the attention dot stays distinguishable from the artwork: minimum ΔE 23.7 at
   32 px and 25.9 at 16 px, with no pixel below 20. Reword §3.2: no **state** colour other
   than attention.

### R13-16 — Recorded deviations the user has not yet accepted · P3 · decision request

- §12 item 1, the TUI's `│` in place of `›`. Its reason (focus ≠ attention) is sound, so
  **R13 recommends accepting it.**
- The review also confirms what testing-strategy §7 left for R13: Alt+←/→ resizes only on the
  focused inspector divider (plain arrows also work), and is otherwise the browser's Back and
  Forward. **R13 confirms this reading of §15 as an accepted exception.** The binding exists
  only while focus is on the separator, and a non-Alt path exists, so no standard shortcut is
  taken from the page.

### Not findings

- **The 2 px horizontal overflow.** The first capture at 1440 px with the inspector open read
  `scrollWidth` 1442. A targeted re-measure (running mission, live map, inspector open) read
  1440, with no element past the edge. Not reproduced, so not recorded.
- **The tray's attention dot does not update while the window is hidden.** The dot is read when
  the menu opens or the window hides, and the shell has no timer. That is B8 as approved. An
  approval arriving while hidden is P20's OS notification (§17). This is noted for P20 and is
  not a finding.
- **The mobile e-stop's PIN.** §19 says "e-stop (confirm + PIN)". No client asks for a PIN for
  the e-stop, because Core's route is `control`. That predates P19 and P19 did not touch it.
  It is listed for the user's P20 credential review, not as an R13 finding.

## 4. Required corrections (the correction pass)

1. **R13-01.** The tray's Emergency stop asks first: a native confirmation with Cancel as the
   default. Update the test and add a mutant.
2. **R13-02.** The offline snapshot names what needs you and what changed, and has the shell's
   gutter. Update the test and add mutants.

After both land: their targeted tests, the P19 mutation suite plus the new mutants, and the
full `tests/v1` run. Then R13 is re-checked on those two items alone.

**Recommended in the same pass, not blocking:** R13-04's TUI list repr and hash placement
(both small and clearly defects), and R13-07's wording.

**For the user to decide:** R13-03 (before P19.5 exit), R13-05, R13-08, R13-11, R13-12,
R13-15 and R13-16.

## 5. Accepted and deferred, with the dispositions already recorded

These were not reopened by this review:

- **Activity chip**: P21 (§46.2).
- **Thread tints**: P22 (§46.2).
- **Row insert and remove**: the V1 exception (§46.2).
- **A-08**: built deliberately in P19.5 (§46.2).
- **Design system §13's Pause-all wording**: amended to what was built (§46.2).
- **Q-A5** (Alt+1/2/3 and Alt+J): decided (§46.3). The bindings in
  `clients/app/tokens/navigation.json` are still Ctrl+1/2/3 and Ctrl+J, as the decision
  allows. The change and its verification across browsers and OSes are due before **P26**.
- **§12 item 86**, "desktop shell" device rows accumulating: not B12's. It belongs to the P20
  credential and remote-access review (item 96).
- **§12 item 83**, the tray's e-stop with Core down: waits for P20's registry kill. R13-01
  concerns the confirmation, not this path.
- **X7**, steering into a running mission: out of P19, needs its own ADR.
- **Items 22, 48 and 90**, the intermittent `test_spa_marker.py`, `test_spa_arrival.py` and
  `test_spa_resources.py`: not design findings, unchanged.
- **`tests/test_cli_help.py::test_a_deferred_v1_verb_imports_only_its_dispatcher`**: fails
  outside `tests/v1`, from before P19 B9, and unchanged.

## 6. Manual verification still outstanding

None of these is claimed. The offscreen Qt test, CI and this review's Playwright captures
replace none of them.

- **Qt shell on a real Windows display:**
  - launch;
  - a restart that keeps the theme;
  - the tray's Pause all;
  - the tray's Emergency stop (after R13-01, with its confirmation);
  - with Core down, behaviour as §12 item 83 records.
- **Offline cold start on a real phone** (after R13-02).
- **Rulebook §34's manual visual acceptance.** Each item is signed off by the user (R5: "do
  not proceed on inferred approval"):
  - BEFORE and AFTER captures on a real Core;
  - a screen-reader pass with live work running;
  - forced colours;
  - 200 % text;
  - the template test.

  R13's captures are evidence for that sign-off, not the sign-off.
- **Carried from P18:** 60 fps at 1,000 nodes on integrated graphics, Windows Terminal and
  conhost, and a physical touch device.

## 7. Disposition

**R13 does not pass yet: a correction pass is required.** Two corrections block it, both small
and both in P19's own client code:

- the tray Emergency stop's confirmation (R13-01);
- the offline snapshot naming what needs you (R13-02).

The rest of the P19 surface conforms to the rulebook and to the P19 gate as approved:

- the mission Now tab, its thread and cards;
- chat approve and reject, and start confirmation;
- directives, plan edit and Appearance;
- T2 on Relations and in the TUI;
- Pause all in the tray, the persistent profile and the unification scenario.

Its remaining findings are wording, document drift and decisions that belong to the user.

On the template test (§33), the reviewer can name what the design is remembered by: the
thread. A fine ink line runs from what Archeus said to the row it touched, once, on Now and now
on the mission tab. This review did not time that line or measure idle; both rest on
`test_spa_thread.py`, `test_spa_mission_thread.py` and the idle-invariant gates, not on the
captures.

P19.5 is not exited, and P20 does not start, until the correction pass has landed, R13 is
re-checked and the user has signed off.

## 8. The user's decisions on R13's findings (2026-10-04)

Recorded as given. None was built in the correction pass, which was limited to the two blockers.

- **R13-03.** Use one "N new messages" row. The digest must not fill the main reading path
  with unnamed "message progressed" rows.
- **R13-05.** A bare `why` inside a mission's conversation means "why this mission?". The
  mission thread supplies the referent.
- **R13-08.** Only one live, actionable approval card per underlying approval. A bare
  `approve` must not create a second live card.
- **R13-11.** No database column or internal storage name in the main Relations reading
  path. Keep whatever the P16 contract actually requires, but not as primary user-facing
  terminology.
- **R13-12.** The action is called **Save preferences**, in the browser and in the TUI.
- **R13-15.** Amend the three stale design documents (theme switching, the TUI changed marker,
  the tray icon colour) to the later approved rules. This reconciles documents; it is not a
  new design decision.
- **R13-16.** Accepted: the TUI's `│` changed marker in place of `›`. Also accepted, as an
  exception: the inspector's Alt+←/→ resize, including that the divider must have focus.

Unchanged: the dispositions in §5 (activity chip → P21, thread tints → P22, row insert/remove
as the V1 exception, A-08, the Pause-all wording, Q-A5 before P26, item 86 → P20, item 83 →
P20, X7, the known intermittent tests and the out-of-scope `test_cli_help` failure).

## 9. Correction pass and second review (2026-10-04)

Correction commit `4e471ef` (p19-design-gate §12 items 99–104), on top of `0558d3a`.

**R13-01: resolved.**
- The change: `run_v1`'s tray item now opens a native `QMessageBox` titled "Emergency stop".
  It shows `gui.ESTOP_CONFIRM`, the sentence the header strip, Control and the chat card
  already use. Cancel is both the default and the escape button. Only the box's own
  "Emergency stop" button calls the unchanged `shell.estop()`.
- Verified in the real offscreen Qt shell (`test_gui_qt.py`): Enter calls no e-stop; the
  button calls exactly one. The title, the sentence, the default and the two buttons are
  checked.
- Mutants P138–P140 are killed. The e-stop semantics are unchanged, including with Core down
  (item 83).

**R13-02: resolved.** Re-checked on a real Core in the 390 px offline cold start: a mission
running, a mission waiting for approval, through the service worker.
- (A) The waiting mission is kept. Offline Needs you reads "Pending Approval · Deploy the
  release notes". Happening now shows only the running mission, as online.
- (B) Since you last looked names the mission rows ("mission Deploy the release notes · needs
  you · 9 events") and the rows Attention ties to a mission ("approval for Deploy the release
  notes · …"). No id is shown.
- (C) The view is in the app frame: a 16 px inset, equal to the online `.main` on the same
  client. Text runs 16–374 px of 390. The scroll width is 390, so there is no sideways scroll.
  There are no commands.
- The tests: `test_offline_needs_you_names_what_waits_and_sits_in_the_app_frame` and the
  amended cold-start test. Mutants P102, P108 and P141–P145 are killed.

**Residual, not blocking (P3).** Rows the kept data cannot name keep their kind alone:
message, policy decision, and an approval already decided (Attention no longer lists it).
They read as before. The message rows are R13-03's (§8). Naming policy decisions and decided
approvals offline would need data B7 does not keep, so it is not done.

**Found while verifying R13-02 (fixed, item 103).**
- The defect: `sender()` returned an unreadable OK body as data. That caused an intermittent
  "reading 'filter'" page error in the cold-start test (3 in about 85 runs before the fix, 0
  in 40 after), and could put the object into the snapshot.
- The cause is established from the stack. A cut-short body is now a network failure.
  `test_a_read_whose_body_never_arrives_is_never_data` covers it, with mutant P146.
- Whether this was item 76's single uncaptured B7 failure is not established.

**No new regression found.** The second review compared the offline and online Now at 390 px
(the same inset and structure; the offline view adds the banner and stays read-only). It
re-read the tray menu: Open, Pause all, Emergency stop, Quit, with Pause all unchanged and no
prompt. The offline view's only visual change is the shared frame.

**Tests.**
- The client: type check and build clean, 225/225 unit tests.
- Targeted: `test_gui_qt.py`, and `test_spa_offline_snapshot.py` (6 tests).
- Full `tests/v1`, `ARCHEUS_E2E=1`: **2568 passed, 0 failed, 13 skipped, 5 xfailed**. The
  three new tests account for the difference from the 2565 baseline. `test_spa_marker.py`
  (item 22) passed in this run. That says nothing about whether it is fixed.
- Mutation: the 27 mutants these changes touch were run (B7's P101–P110, B8's Qt mutants
  P126, P127 and P129–P131, and the new P138–P146) and **27/27 were killed**. The full
  P01–P146 pass was **not rerun**.

**Manual checks: still outstanding (§6), none claimed.**
- On a real Windows display: launch, the theme surviving a restart, the tray's Pause all, the
  tray's Emergency stop (now with its confirmation) and Core down.
- The offline cold start on a real phone. Repeat it, since R13-02 changed the offline layout.
- The user's §34 sign-off.

**Disposition: R13 passes.** The two blocking findings are resolved in the implementation.
R13-03 to R13-16 remain as recorded, with the user's decisions in §8. P19.5 exit still needs
the manual checks and the user's sign-off. P20 has not started.
