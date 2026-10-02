# Archeus V1 — Design System ("Quiet instrument, living thread")

Status: **DECIDED** for principles, semantic roles, state model and accessibility floors;
**PROPOSED** for exact hex values (validated by the contrast gate in P16 before they freeze).
Research and rationale: [ARCHEUS_V1_DESIGN_RESEARCH.md](ARCHEUS_V1_DESIGN_RESEARCH.md).
UI structure: [../architecture/ui-architecture.md](../architecture/ui-architecture.md).

> **Amended 2026-09-30** (ADR-0024…0028, user directive; the visual rulebook is
> [ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md](ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md)).
> Where this document and the rulebook differ, the rulebook governs. In short: Visual DNA "dark
> and still until Archeus acts" with an activity **halo**, execution **pulse**, travelling
> **marker** and the **thread** (§2, §8); one motion registry and the idle invariant (§8); the
> thread's T1 form is drawn from `Message.links` and **the left edge of a row belongs to the
> thread** (§2); legacy palettes survive only as thread tints (§3.3, ADR-0026); `focus` moves to
> thread ink because `#FFD166` is ΔE 12.3 from attention (§3.3, ADR-0028); overlays are opaque
> and depth/transparency are fixed tokens (§6); the mark and its orbit enter the shell (ADR-0027).

This is a product language, not a component library. It says what Archeus looks like *because of
what Archeus is*: a persistent colleague whose work you glance at, verify and direct.

---

## 1. Design philosophy

1. **Quiet by default, loud only when it means something.** Surfaces, type and spacing carry
   hierarchy. Colour is reserved for *state* and for the *thread*. If everything is quiet, a
   single amber diamond on a phone is enough to say "you are needed".
2. **State is the content.** The most important pixels on any screen say what is true, who owns
   the next step and what happens next. Decoration never competes with them.
3. **The system is alive because things change, not because things move.** Motion only reports
   change (a task finished, Archeus touched an object, a stream is producing output).
4. **Proof on demand.** Every consequential element has a *Why* affordance. Evidence is one step
   away, never zero (clutter) and never three (distrust).
5. **Point of view with restraint.** One signature element (the thread). Everything else is
   craft: alignment, rhythm, consistent iconography, honest typography.
6. **Same language on every surface.** Desktop, web, mobile and TUI share roles, glyphs, state
   names and copy. Density and interaction adapt; meaning does not.

Checked against the Apple Design Skill's template test: the plan is specific to Archeus (state
colours + thread + inspector *Why* only make sense for an agentic system you must trust), so it is
not a default. Its dark appearance is *not* "near-black + acid accent": after design review B.1 there is no hue
accent at all — primary actions are neutral fills, the thread is near-white ink, and the only hues
on screen are state glyphs and labels.

## 2. Signature element — the thread

A fine luminous line (1 px at 1×, 1.5 px at ≥ 2×; colour `thread`) that links **an Archeus
action to the world object it touched**:

- In the conversation: from a message to the card or object it acted on (e.g. "Pinned *Standup 21
  Sep* into *Dashboard*" draws a line to the Dashboard row in *Happening now*).
- In lists: a 2 px left rule on rows Archeus changed since the user last looked (fades out on
  acknowledgement).
- In the spatial view: the edge Archeus is currently traversing (live execution energy).

Rules: appears only when Archeus acts; never decorative; max one travelling animation at a time
(transform/opacity only, ≤ 600 ms); under reduced motion it appears without travel; under High
Contrast it becomes a solid 2 px line in `focus` colour. **Removal test:** without the thread,
the user loses the visible connection between what Archeus *said* and what it *did* — so it
stays; nothing else gets a signature.

*As built (P19.5, R6):* the conversation form on Now — a new Archeus message whose `Message.links`
name an object with a row on screen draws one line from the message to that row, drawn on and
gone; what stays is the list rule (on the row, and on the message's card or link) while the digest
names the object; the polite live region says "Archeus updated …". Thread tints and the mission
Now tab are not built yet (no curated tint list; per-mission conversations are P19's).

## 3. Colour system

### 3.1 Roles

| Role | Use | Never |
|---|---|---|
| `bg` | app background | text |
| `surface-1/2/3` | base panel, raised panel (inspector), overlay (sheet, popover) | state |
| `line` / `line-strong` | hairline separators, input borders | emphasis |
| `text` / `text-2` / `text-3` | primary, secondary, tertiary text | on coloured fills below contrast floor |
| `primary` | fill of the one primary action on a view — a **neutral** inverted fill (`text` on `bg`), never a hue | state |
| `thread` | the signature line only (§2) — near-white on dark, near-black ink on light | anything else |
| `link` | inline links: `text` colour + underline | colour-only links |
| `focus` | focus ring (2 px, offset 2 px) | anything else |
| `state.*` | state glyphs, status labels, subtle row tints (≤ 12% alpha) | buttons, links, the thread |

### 3.2 Semantic state colours (fixed across all themes)

| Token | Meaning | Dark (proposed) | Light (proposed) | Glyph |
|---|---|---|---|---|
| `state.active` | working now | `#5AA9FF` | `#0B63CE` | ● |
| `state.attention` | needs the user | `#F2B544` | `#9A6100` | ◆ |
| `state.blocked` | cannot proceed, not waiting on user | `#F07178` | `#B3261E` | ■ |
| `state.paused` | paused by someone | `#A7B0BD` | `#5B6472` | ‖ |
| `state.thinking` | understanding/planning | `#B79CFF` | `#6A45C9` | ◌ |
| `state.done` | verified and accepted | `#5FD08B` | `#1E7F45` | ✓ |

- **Never colour alone:** every state is glyph + label (+ colour). The glyph set above is also the
  TUI's.
- **Red means "a problem needs resolving"** and is shared by Blocked (■) and Failed (✕); glyph and
  label distinguish them. (The first draft gave Failed its own orange; measured ΔE was 22 on dark
  and 11 on light — two colours nobody could tell apart claiming two meanings. Design review B.1.)
- **No state colour is also an interface colour.** Primary actions are neutral fills and links are
  underlined text, so the only hues on a screen are states. (The first draft's blue accent sat
  ΔE 18 from `state.active` on dark and was identical to it on light. Design review B.1.)
- `attention` is the only colour allowed to appear in the tab bar badge and the tray icon.

### 3.3 Themes

| Theme | Status | Notes |
|---|---|---|
| Archeus Dark | the OS default under System; selectable (ADR-0044) | `bg #0E1116`, `surface-1 #141922`, `surface-2 #1A2130`, `text #E6EAF0` (14.6:1 on surface-1), `text-2 #AAB3C0` (8.3:1), `primary` fill `#E6EAF0` with `#0E1116` label, `thread #F4F1EA`, `focus #F4F1EA` (thread ink — was `#FFD166`, ΔE 12.3 from attention; ADR-0028; built in P19.5 slice 1; light: `#11151C`) |
| Archeus Light | the OS default under System; selectable (ADR-0044) | `bg #F7F8FA`, `surface-1 #FFFFFF`, `text #11151C` (18.3:1), `text-2 #4A5463` (7.7:1), `primary` fill `#11151C`, `thread #11151C` |
| High Contrast (dark + light) | follows `prefers-contrast: more` / Windows contrast themes (`forced-colors`), or the High contrast preference (ADR-0044) | solid surfaces, 7:1 body text, 2 px lines, no tints |

Appearance **follows the operating system by default** (`prefers-color-scheme`,
`prefers-contrast`, `forced-colors`, `prefers-reduced-transparency`). *Amended 2026-09-30 by the
user's decision D-21 (ADR-0044; to be implemented in P19):* the user may override it per client with a theme
(System · Dark · Light) and a contrast (System · Standard · High) preference; `forced-colors`
always wins; the choice is applied before first paint and works offline. The application themes
are exactly the three above; appearance choices otherwise remain thread tint, density and motion.
(The earlier rule — no app-level switch, after `dark-mode.md` — is superseded for Archeus because
it runs inside browser, PWA and Qt shells whose appearance the user often cannot set per app.) Measured contrast of every state glyph colour on
`surface-1`: dark 6.2–9.6:1, light 5.0–6.5:1 (all ≥ 4.5:1, so state *labels* may use them too).

Legacy `themes.PALETTES` (39 authored palettes) survive **only as thread tints** — an application
theme and a thread tint are different things, and no palette becomes an application theme; surfaces and state colours do not change. Skins and worlds are not
carried into the V1 client (ADR-0017): they redefine chrome per look, which conflicts with fixed
state semantics. The legacy GUI keeps them until it retires. The build rejects a thread tint
that fails 3:1 against `surface-1` or collides (CIE76 ΔE < 30) with any state colour.

Contrast floors, enforced by `tests/v1/design/test_contrast.py` over every theme × role pair:
text ≥ 4.5:1 on its surface; `text-2` ≥ 4.5:1; `text-3` ≥ 3:1 and never for essential content;
state glyphs ≥ 3:1 on `surface-1`; focus ring ≥ 3:1 against both the control and the surface.

## 4. Typography

| Role | Desktop | Mobile | Weight | Use |
|---|---|---|---|---|
| `display` | 28/34 | 28/34 | 600 | Now greeting line only |
| `title-1` | 20/26 | 22/28 | 600 | view titles |
| `title-2` | 16/22 | 18/24 | 600 | section and inspector titles |
| `body` | 13/20 | 17/24 | 400 | default text (HIG floors: 13 desktop, 17 mobile) |
| `body-strong` | 13/20 | 17/24 | 600 | emphasis in rows |
| `caption` | 12/16 | 13/18 | 400 | metadata (never below 10 desktop / 11 mobile) |
| `mono` | 12/18 | 14/20 | 400 | ids, commands, diffs, numbers in tables |

- Families: `"Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, Roboto, sans-serif`
  for text; `"Cascadia Mono", Consolas, ui-monospace, "SF Mono", monospace` for mono. No web
  fonts, no CDN (offline, and the repo's rule).
- Sizes are rem-based; the app root follows the OS/browser text size; layouts survive 200%.
- Numbers use tabular figures (`font-variant-numeric: tabular-nums`).
- Copy style: sentence case for everything except proper nouns; labels say what happens ("Approve
  push", not "Submit"); progress text is specific ("Running 214 tests in Payments").

## 5. Spacing, layout and grid

- 4 px base unit; scale `0 2 4 8 12 16 24 32 48 64`.
- Density modes: *comfortable* (default) and *compact* (desktop only; row height 28 → 24).
- Desktop layout: sidebar 232 px (collapses to a 56 px icon rail below 1000 px of window), main
  flexible, inspector 360–560 px resizable; content max line length 72ch for prose.
- **Component layout reads its container, not the window** (container queries; carried from the
  current repo's hard-won rule). Only chrome (sidebar rail, tab bar vs sidebar) uses media queries.
- Lists over cards: a mission is a row, not a card, except inside the conversation where cards
  are the unit.

## 6. Surfaces, borders, radius, elevation, materials

| Layer | Surface | Border | Radius | Elevation |
|---|---|---|---|---|
| Base (lists, views) | `surface-1` | none; `line` separators | 0 | 0 |
| Raised (inspector, cards in conversation) | `surface-2` | 1 px `line` | 8 px | shadow `0 1px 2px rgba(0,0,0,.24)` |
| Overlay (sheets, popovers, command bar) | `surface-3` | 1 px `line-strong` | 12 px (sheets: 16 top) | shadow `0 8px 24px rgba(0,0,0,.32)` |
| Controls | inherit | 1 px `line` | 6 px | 0 |

- **Transparency:** overlays are opaque `surface-3` (amended 2026-09-30; was "may use 92–96%");
  depth and transparency inside the graph are the fixed tokens of ADR-0028; no `backdrop-filter`, no blur,
  no blend modes (they tear the Qt WebEngine GPU surface — verified in the current repo — and
  cost readbacks everywhere). Reduced transparency → 100% opaque.
- No gradients on surfaces. The only gradient allowed is the thread's travelling highlight.

## 7. Iconography

- One outline icon set, 1.5 px stroke at 20 px, drawn on a 24 px grid; filled variants only for
  selected nav items. Proposed base: a permissively licensed set vendored into the build (no CDN).
- Every icon has a text label or an accessible name; icon-only buttons are allowed only in
  toolbars with tooltips and names.
- Object-kind icons (mission, project, repository, decision, person, meeting, knowledge, idea,
  automation, account) are consistent across list, inspector, graph and TUI (TUI uses letters:
  M P R D @ N K I A $).

## 8. Motion

| Motion | Duration | Easing | Trigger |
|---|---|---|---|
| State change (glyph cross-fade + 2 px lift) | 160 ms | ease-out | domain state changed |
| Row insert/remove | 200 ms | ease-out | list changed (keyed reconcile) |
| Inspector slide | 220 ms | ease-out | open/close |
| Sheet (mobile) | 280 ms | spring-like ease-out | open/close |
| Thread travel (built on Now, P19.5 R6) | ≤ 600 ms, once | ease-in-out | Archeus acted on an object |
| Active pulse (built on the graph; on mission rows since P19.5 R5) | one 240 ms opacity pulse per batch of new output, at most every 2 s, ≤ 12 concurrent on the canvas | ease-out | execution stream produced events |
| Activity halo (2026-09-30; built on the graph) | static — no animation; appears on the first live read, clears when a read shows the work ended | — | presentation class `active` |
| Travelling marker (2026-09-30; built on the graph) | 600 ms once per output batch, ≤ 8 concurrent (oldest dropped) | linear along the edge | `execution.*` frame on a drawn live edge |
| Activity chip (2026-09-30) | fade 160 ms, TTL 2.5 s (4 s on error), ≤ 3 per row | ease-out | a re-read execution's current action |
| Presence orbit (2026-09-30; built in the shell, P19.5 R7) | one 900 ms turn of the mark's node round its orbit, ≤ 1 per 5 s, parked where it began; none under reduced motion | ease-in-out | a batch of `execution.*` frames |

Every row above is also an entry in the motion registry (ADR-0024); no animation exists outside it,
none runs while idle, and none replays after a re-read or reconnect.

**The registry as built (P19.5, 2026-09-30).** `clients/app/tokens/motion.json`, validated and
generated by `tools/gen_ui.py` into `src/state/motion.ts` (the TUI animates nothing and gets no
copy). Each entry: status (`built` / `approved`), source, trigger, `driven_by` (event / user /
state — only a static entry follows state), `runs_on` (css / loop / static), its bindings (keyframe
names, transition selectors), `max_ms` (null = static), token, easing, cap / `cap_per` / `over_cap`,
min interval, surfaces, idle (never / static), `replay: false`, the reduced-motion behaviour and
the text equivalent. The active pulse is recorded as built — a linear 240 ms opacity ramp — and its
approved cap of 12 is now enforced. Two clocks: an event's time is its place in Core's log (the SSE
id, `events.seq`); a presentation's time is the page's. `src/state/timeline.ts` holds the running
presentations at module scope (a rerender, remount or route change never makes a new one), refuses
an event at or below the newest seq it presented for that motion (no replay, and a running one keeps
its start), refuses under reduced motion while counting the event as presented, and answers
`at(t)` / `progress(motion, t)` as a pure read — `renderAt(t)`.

**The activity halo as built (P19.5, 2026-09-30), on the graph.** *Active work* is Core's own
state: a node carries a halo when its presentation class, from the `state` the graph read returned,
is `active` (`model.haloed`) — an execution INTENT / STARTING / RUNNING / HANDING_OFF, a mission
EXECUTING, a task RUNNING, and the rest of the class. No frame, message, recent render or mount
makes one. *Completion* is a read showing another state; *hysteresis* is the read the view holds —
the cache keeps it across a lost stream, a resync and a failed re-read, so the halo never clears on
a reconnect (a remount after the cache dropped the read draws nothing until the next read, and then
the truth). It is two static 1 px strokes of `--state-active` at `--halo-inner` (.70) and
`--halo-outer` (.35) (ADR-0028 §3; the two alpha tokens were added to `tokens.json`), 2 and 6 units
outside the node's radius — inside and outside the focus ring, so a focused live node shows both;
the offsets are a layout choice this slice made, no document gave them. Forced colours or reduced
transparency draw one solid ring. It is drawn into the static layer before the nodes: no frame, no
timeline entry, the same under reduced motion. Its text equivalent is the node's state word in the
graph mirror and "live work now" beside it. The row-glyph ring (rulebook A-03) is not built yet.

**The travelling marker as built (P19.5, 2026-09-30), on the graph** (ADR-0024 §5-6, rulebook §21
A-04). *What qualifies:* an `execution.*` stream frame whose `subject` is an execution loaded in the
graph read with a drawn `executions.task_id` edge that is live (its execution's presentation class
is `active`) — one marker per frame, i.e. per batch of output. A frame about another kind, another
event, an execution not in the read, an ended execution or a frame with no seq sends none.
*Source and target are Core's:* the source is the frame's execution and the target is the task at
the other end of the edge Core recorded, both as drawn (lifted to a visible ancestor inside a
collapsed group); never geometry, adjacency, a recent render or a guess, and no Core change. The
execution → produced-object causality marker is a different thing and stays with P21 (Q-B1).
*Travel:* a straight line from the source's position to the target's at constant speed (linear
easing), the head at progress p of the registry's 600 ms, a 3 px `--thread` head and a 12 px tail
behind it that never passes the source, both in screen pixels whatever the zoom; all tails are one
path and all heads another, drawn over the static-layer copy after the pulses, so no node or edge
changes and no layout moves. *Cap:* 8 at once on the canvas, the oldest dropped by the timeline;
one execution's successive batches are separate markers on the same edge. *No replay, reconnect,
remount:* started through the page's one timeline with the frame's seq, so the same seq heard again
(a reconnect, a resync, a second tab, a remount or a route change) starts nothing and a running
marker keeps its start; only a newer seq starts another. *Idle:* each marker is one registered
`Loop.animate('travelling-marker')` of 600 ms; with none running the loop parks and schedules no
frame. *Slow frames* (`Loop.degraded`): a marker takes the pulse's form (one opacity step over its
edge, no travel), per rulebook §21-22. *Reduced motion:* no marker is drawn, the event still counts
as presented (turning reduced motion off replays nothing), and the live edge is drawn 2 px and
static. *Text equivalent:* in the graph mirror the execution's relation to its task reads
"… — live now"; the mirror never narrates the animation. The operations-map surface is not built.

**Adding a motion** (every later P19.5 slice): (1) give its entry the approved values, never new
ones; it stays `approved` until the code runs it; (2) when built, set `built` and bind it — a CSS
motion names its keyframes or transition selectors, a canvas motion is started through
`timeline.start(id, target, frame.id, now, reduced)` and scheduled with `Loop.animate(id)`, which
takes a registered built loop id and never a duration; (3) draw its reduced-motion equivalent and
its text equivalent; (4) add its read to `test/motion-harness.ts`'s `renderAt`, test it at t = 0,
mid and end, and add its mutants to `tools/mutate_p19_5.py`. `py tools/gen_ui.py`, the design
gates, `test/motion.test.ts` and `tests/v1/e2e/test_spa_motion.py` fail an animation that skips
any step.

Rules (carried from the repo and the HIG): animate only `transform` and `opacity`; no ambient
loops; nothing loops — the active pulse fires once per batch of real output (design review B.5 replaced
the first draft's breathing glyph, which was an ambient loop on the most-watched element);
one animation loop for the whole app that parks when the window is hidden or blurred; reduced
motion → cross-fades only, no travel, no breathing. A test parses every keyframe and rejects
other properties (as `tests/test_gui_flicker.py` does today).

## 9. Interaction states

| State | Treatment |
|---|---|
| Hover | row tint `text` at 4% alpha; pointer cursor on interactive elements |
| Pressed | tint 8%; scale 0.98 on buttons (transform) |
| Focus | 2 px `focus` ring, 2 px offset, always visible on keyboard focus (`:focus-visible`) |
| Selected | 2 px `text` left rule + `surface-2` background |
| Disabled | 40% opacity **plus** a reason in the tooltip/accessible description ("Needs the approve scope on this device") |
| Loading | skeleton rows for lists (static, no shimmer loop); inline spinner only inside a control; specific progress text |
| Empty | one sentence saying what will appear here and one action ("No missions yet. Tell Archeus what you want.") |
| Error | inline, next to the thing; says what happened and what to do; never a modal for a recoverable error |
| Success | the state change itself (✓) plus a transient toast only when the success happened off-screen |
| Warning | `attention` glyph + text; used for "this will need approval", "stale knowledge" |

## 10. Work-state vocabulary (the heart of the system)

Presentational states map domain states (see
[../architecture/state-machines.md](../architecture/state-machines.md)) to one glyph, one colour
role and one label pattern. The mapping is one table in `clients/app/src/state/presentation.ts`
generated from `archeus/core/domain/states.py` so UI and domain cannot drift.

| Presentation | Glyph | Label pattern | Domain states |
|---|---|---|---|
| Active | ● | "Implementing chart components" (current task title, present participle) | EXECUTING, RUNNING, VERIFYING, REVIEWING, STARTING |
| Needs you | ◆ | "Waiting: approve plan v2" / "Waiting: accept the video" | APPROVAL_REQUIRED, AWAITING_APPROVAL, AWAITING_HUMAN, acceptance-BLOCKED |
| Blocked | ■ | "Blocked: all eligible accounts at ceiling · resets 16:05" | BLOCKED (not on user), CONFLICT, LIMITED (accounts) |
| Paused | ‖ | "Paused by you 11:40" / "Pausing 2 executions…" | PAUSED, PAUSING |
| Planning | ◌ | "Planning: reading Monday's notes" | CREATED, UNDERSTANDING, CONTEXT_GATHERING, REASONING, PLANNING, REPLANNING |
| Verifying | ● + "Verifying" label | "Verifying: 214 tests" | VERIFYING (a sub-label of Active, same colour) |
| Done | ✓ | "Done 14:20 · verified · reviewed" | COMPLETED, SUCCEEDED, PASSED, MERGED |
| Failed | ✕ (red, shared with Blocked) | "Failed: tests still failing after 2 replans" | FAILED, ENDED_ERROR |
| Inactive | – | "Cancelled" / "Archived" | CANCELLED, ARCHIVED, SUPERSEDED |

**Approval required** always renders the canonical action (command/target/diff hash) in `mono`
with the policy reason underneath, and two buttons of equal size; destructive approvals put
Reject on the leading side and require step-up.

**Verification** results render as a checklist of named checks with pass/fail glyphs and a link
to the output artifact; `independent = false` reviews carry a caption "reviewed on the same
account — no other resource was free".

## 11. Components (product components, not a generic kit)

| Component | Purpose | Key rules |
|---|---|---|
| **Mark and operations strip** | the shell header on every page (ADR-0027 §1-3) | *As built (P19.5, R7):* the credited glyph (`MARK` in `state/orbit.ts`, the site's figure) in `currentColor` at 20 px beside "Archeus", and on the boot screen with "Connecting to Archeus…"; nowhere else. Its orbit's node is the presence — hollow while not connected, `state-attention` while something needs you, `state-active` while an attempt runs, neutral otherwise — and the favicon shows the same state still, on the dark tile; the app icons are the tile mark. The strip is a `nav` named Operations: "N running · N needs you · N clients", each a link to its list, the freshness of the status read, and Emergency stop behind its confirmation, or "Emergency stop engaged" while Core reads it disarmed; its words go to a status region at most once per 30 s, only on a change. A phone shows the mark and the counts. Pause all joins it with R10 |
| **Presence line** | top of Now: "Archeus · working on 2 missions · 1 needs you" | derived from counts, never personality text |
| **Digest** | since-you-left grouped list | every bullet links to its object; Dismiss advances the per-user cursor |
| **Mission row** | one mission in any list | glyph, title, project, status line, waiting-on, age; no tokens/sessions. *As built (P19.5, R5):* an `execution.*` frame about a running attempt, its mission read again from Core, plays one 240 ms opacity step over the row (`row-pulse`), at most once per 2 s, never for an event already presented, never under reduced motion or slow frames; the state word is its equivalent (Core records no last-output time). Like every row the digest can name, it carries the T2 rule and "changed since you looked" while Core's digest names it. The activity chip is not built: its text has no source yet |
| **Card** (conversation) | live view of an object inside a message | types: mission proposal, plan, approval, route explanation, diff, verification, digest; updates live; shows "inferred" chips |
| **Challenge block** | Archeus disagrees or asks | two explicit choices as buttons; never a yes/no on prose |
| **Inspector** | canonical detail of any object | fixed tabs per kind; *Why* tab always last-but-one; Timeline last. *As built (P19.5, R1):* titled by a noun or the object's own name, never its id; its identifiers are the header's **Details** |
| **Details** | an object's identifiers, for inspection and support | *As built (P19.5, R1 with the minimum of R9; rulebook §15):* one native `<details>` (`components/ui.tsx` `Details`), closed by default, summary "Details"; rows only (`dl.kv`), each label saying what the identifier names ("Account id", "Mission branch (git)", "Action hash (what an approval is bound to)"); scalars only, so JSON cannot reach it; on the inspector header, the approval card, an automation, an account, a project and its repositories, each repository inspection (its git revision), and an output event that carries ids or digests. The default view names objects instead: a reference reads as its kind and title (`RefLabel`), an account as its label (`AccountName`), and an id inside a sentence Core wrote becomes a link to that object (`Prose`, from `ID_KINDS`, which `tools/gen_ui.py` derives from Core's `ids.PREFIXES`). Which fields are identifiers is decided by name (`state/present.ts` `technical`), never by guessing at a value |
| **Why panel** | explainability | three sections: Context used (with reasons), Policy (matched rules), Route (candidates × reason); raw record toggle |
| **Attention item** | one thing needing the user | kind icon, one-line ask, primary + secondary action, due/expiry |
| **Plan list** | task DAG as indented list with lanes | current task highlighted; approval points marked ◆ |
| **Resource row** | account with priority handle, ceiling slider, utilisation bars, health | reserve shown as hatched band; health glyph |
| **Policy grid** | action classes × scope | locked cells show a lock; simulate box |
| **Composer** | intent input | supports control verbs, `@` object mentions, file drop (meeting notes); shows "Archeus will…" preview for control verbs |
| **Command bar** | ⌘/Ctrl+K anywhere | same parser as composer + jump-to-object |
| **Graph view** | spatial inspection | encoding in research §26; keyboard traversal; list fallback. *As built (P18):* `src/graph/encoding.ts` is the table (session ring, DECISION diamond, state colour on missions/tasks/executions only, neutral elsewhere); motion is one camera move and one edge pulse, both removed under reduced motion; below 600 px the Relations list. *As built (P19.5, R2; ADR-0025 §1-2):* a **legend** under the canvas, open by default and collapsible (`src/graph/legend.ts`, rows read from `encoding.ts`): Shapes (every kind in the loaded picture, a DECISION as "decision", an endpoint as one row), Lines (only the tiers loaded edges carry: "recorded", "suggested by Archeus", "unclear" once Core writes one) and Live work (the halo, "live work now", and the marker — the static thicker edge under reduced motion); each Shapes and Lines row is a checkbox that hides what it names from the drawing only; each swatch is drawn with the renderer's own shape, dash, halo rings and thread ink (`drawSwatch`). **Expand all** / **Collapse all** in the toolbar and E / C on the canvas set the same expanded set Space toggles one entry of; view state only. *As built (P19.5, R3; ADR-0025 §3-4, ADR-0028 §3):* the **constellation treatment** — a drawn project with drawn members sits in a **hull**, one filled path under the strokes in `text` ink at `hull` .06 (`hull-focus` .10 when the focus is in it), a 1 px outline under forced colours or reduced transparency; **depth** by drawn hop distance from the focus (0–1 full, 2 at `alpha-tier1` .64, 3+ at `alpha-tier2` .36); a **live node** carries a **core** of thread ink inside its shape; edges **recede** to `alpha-recede` .40 except a recorded edge of the focus and the selected, path and live edges, each keeping its tier's dash. **"What does this affect?"** (toolbar toggle on the focused node, 1–3 steps, default 2, Esc leaves it) highlights what is reachable over recorded relations in the loaded view and says so in a status line and the mirror. The mirror says the hull and depth too: "in project Atlas", "2 steps from …" (rulebook §20). All view state |
| **Toast** | off-screen success/failure | max one at a time, 4 s, never for errors needing action |

## 12. Accessibility rules (floors, gated)

- Contrast floors in §3; High Contrast themes.
- Keyboard: every action reachable; logical tab order; skip link to main; list navigation with
  arrow keys; `Esc` closes the topmost overlay; shortcuts discoverable in the command bar.
- Screen readers: landmarks (nav, main, complementary for inspector); cards are `article` with
  a label; streaming progress in a polite live region, rate-limited to one announcement per 5 s;
  new approvals announced assertively once; Archeus messages labelled as AI-generated; graph view
  exposes a list equivalent.
- Targets: 28×28 px desktop (20 minimum for dense toolbars), 44×44 pt mobile.
- Text scaling to 200% without clipping or horizontal scroll at 390 px wide.
- No information by colour alone; no information by motion alone.
- Reduced motion, reduced transparency and forced colours (Windows High Contrast) honoured.
- Time limits: approvals show their expiry and can be extended.

## 13. Desktop adaptation

Sidebar (one level, with sub-sections inside Control only — two levels max; nothing critical at
its bottom edge — *Pause all* lives in the Now header, the tray and the command bar), inspector column,
tray menu (Open, Pause all, Emergency stop, Quit), native notifications, standard shortcuts
(⌘/Ctrl+K, ⌘/Ctrl+1–4 destinations, ⌘/Ctrl+. pause focused mission, `?` shortcuts), right-click
menus on rows, drag to reprioritise, resizable columns, compact density.

## 14. Mobile adaptation

Bottom tab bar (Now, Work, World, Attention) with the attention badge; Control behind the avatar
menu; sheets for approvals and inspectors (grabber, swipe to dismiss, one at a time — swiping an
approval sheet away means **decide later**, never reject; the item stays in Attention); pull to
refresh (re-query); safe areas; one-handed reach — primary actions in the lower half; no hover
dependence; step-up PIN pad for destructive approvals; comfortable density only.

## 15. TUI equivalents

| GUI element | TUI |
|---|---|
| State glyph + colour | same glyph when the terminal font has it, else the ASCII set `* ! # = ~ + x` (active, needs you, blocked, paused, planning, done, failed) chosen by a startup probe; ANSI colour from the token table (nearest non-system 256-colour, never 0–15, as `themes.hex_to_x256` does today); monochrome safe. *As built (P17):* the ASCII glyph of every presentation class lives in `presentation.json` (also `o` proposed, `^` approved, `.` neutral, `-` inactive); the probe is the output encoding, and `ARCHEUS_TUI_ASCII=1` forces it |
| Sidebar destinations | top line `1 Now 2 Work 3 World 4 Control ◆2 attention` |
| Inspector | full-screen pager with tab keys `o p n e t w l` (outcome, plan, now, evidence, thread, why, timeline). *As built (P17, p17-design-gate A6):* the keys come from `navigation.json`; the mission's are `o p n e w t r` (outcome, plan, now, evidence, why, timeline, relations). **There is no Thread tab**: P16 never built one (p16-design-gate §30 deviation 10), so `t` is Timeline and Relations has `r` |
| Cards | boxed blocks with the primary action key shown (`[a] approve  [r] reject`). *As built (P17):* commands are upper-case keys on the hint bar (`[A] Approve plan  [R] Reject`), so no command shares a key with a tab or a destination |
| Composer / command bar | `:` command line with the same grammar |
| Thread | `›` marker on rows changed since last look |
| Toasts | status line message, 4 s |
| Motion | none |

## 16. Tokens (single source)

`clients/app/tokens/tokens.json` (hex-first, like `themes.py`) generates:
`clients/app/src/styles/tokens.css` (CSS custom properties), `clients/app/src/tokens.ts`,
`archeus/cli/tui/tokens.py` (ANSI). A test regenerates and compares, and the contrast test reads
the same file. Adding a component never edits tokens; adding a theme never edits components.

```json
{
  "space": [0, 2, 4, 8, 12, 16, 24, 32, 48, 64],
  "radius": {"control": 6, "raised": 8, "overlay": 12, "sheet": 16},
  "type": {"body": {"desktop": [13, 20], "mobile": [17, 24]}},
  "motion": {"state": 160, "row": 200, "inspector": 220, "sheet": 280, "thread": 600},
  "themes": {
    "dark": {"bg": "#0E1116", "surface-1": "#141922", "text": "#E6EAF0",
             "primary": "#E6EAF0", "thread": "#F4F1EA", "state.attention": "#F2B544"}
  }
}
```
