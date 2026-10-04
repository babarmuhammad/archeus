# Archeus V2 UI Architecture

**Status: ARCHITECTURE — DIRECTION RECORDED, NOT IMPLEMENTED.** This document defines the
architecture that V2 UI implementation will follow. It is not an implementation plan, and it
starts no implementation. Here is what is decided and what is not:

- **Decided:** the direction the user gave on 2026-10-04, recorded in rulebook §46.4:
  - S-1, S-2 and S-3 as V1 corrections;
  - V-D1, V-D2 and V-D3;
  - V-D4 and V-D5, gated on prototypes.
- **Proposed:** everything else, until it becomes an ADR or a design rule the user approves
  (§T).
- **V1 still governs.** The V1 rulebook
  ([ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md](ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md))
  governs V1 until P26. This document amends it only in the single §27 clarification that V-D1
  required. "Do not proceed on inferred approval" (rulebook §0, R5) applies.

**Sources:**

- [ARCHEUS_V2_UI_RESEARCH.md](ARCHEUS_V2_UI_RESEARCH.md) (the research; cited as *R*);
- [ARCHEUS_V2_VISUAL_DIRECTION.md](ARCHEUS_V2_VISUAL_DIRECTION.md) (visual impact, the JARVIS
  benchmark; cited as *VD*);
- [../research/2026-10-v2-ui-reference-study.md](../research/2026-10-v2-ui-reference-study.md)
  (the evidence, `E-n`).

Date 2026-10-04. Branch `archeus-v1-rearchitecture`.

**The design objective, kept visible throughout.** Archeus should be more visually compelling
than the typical JARVIS-style AI interface, without becoming another JARVIS clone. That means
more presence, identity, depth, emotional impact, clarity and visible intelligence — while
staying calm enough to use every day. It should make someone think *"this feels like a real
intelligent system"*, not *"this looks like a Three.js JARVIS demo"*.

## Contents

A. Visual principles · B. Visual identity · C. Motion system · D. State visualization · E. Depth
and material · F. Typography · G. Colour · H. Attention · I. Mission lifecycle · J. The luminous
thread · K. Hero moments · L. Relations · M. Mobile · N. TUI · O. Offline · P. Accessibility ·
Q. Performance · R. Technology policy · S. V1/V2 boundary · T. Decisions, gates and the next
phase · U. JARVIS differentiation matrix · V. The "more compelling than JARVIS" test

---

## A. Visual principles

Five principles (VD §17). Every V2 visual proposal is checked against all five, and against the
anti-pattern list (VD §14).

| # | Principle | Rule |
|---|---|---|
| **V-1** | **Light is evidence** | Only Core-recorded work emits light. Light travels only along a recorded path. Every light answers "why" on hover or focus. At idle there is no light beyond static state marks. |
| **V-2** | **Stillness is the canvas** | Zero animation frames at idle (V1's invariant). The resting interface earns its beauty from typography, alignment, tonal depth and fine line. |
| **V-3** | **Depth means focus** | Opaque planes. Elevation by lightness, edge light and a static shadow. The focus plane is the only depth motion. No blur, glass, parallax or 3D in the app. |
| **V-4** | **Objects persist** | Going from an object to its detail transforms that object. Peer navigation is a quick fade. Nothing vanishes and reappears elsewhere. |
| **V-5** | **Intensity is earned** | The Visual Impact Ladder (§C.2): each moment's intensity follows its significance and falls with its frequency. Hero moments are rare and gated. Unresolved attention changes form rather than repeating. |

**Why these beat a HUD [I]** (VD §20–§23). Salience is relative. Against a still, dark,
well-ordered ground, one point of moving light is the most conspicuous thing on the screen —
peripheral motion is detected in about 1 s, with under 2 % misses (E-49). A HUD animating
everything at once has no ground, so nothing in it can stand out. Archeus gets its drama from
the **contrast between stillness and real activity**, which a permanently animated interface
cannot have.

---

## B. Visual identity

**The signature: the luminous thread** (V-D2, decided as the leading direction; not
implemented). It is a line of light that runs from what Archeus said or decided to the thing it
changed, lands, and leaves a trace. It extends into a product-wide grammar (§J) linking intent →
plan → approval → execution → resource → result → review, and cause → effect in Relations.

**Why the thread, and not an orb or another candidate** (VD §16, §25, §26):

- **It is true by construction.** It fires only on a Core-recorded action with links, so it
  cannot run while nothing happens.
- **It is unique to an agent system.** It visualises the one thing a JARVIS orb never shows:
  *consequence* — words becoming changes in the world.
- **It costs nothing to render:** SVG and CSS, transform and opacity, 0 KB.
- **It exists in every medium:** the T1 line, the T2 rule, the TUI's `│`.
- **It cannot fatigue faster than Archeus acts:** one travel at a time, with surplus collapsing
  into traces.

**The centre of gravity is not an invented core** (VD §26). Archeus already has three, one at
each scale, and all three come from the domain model:

| Scale | Centre of gravity | Already in V1 as |
|---|---|---|
| System | **The mark and its orbit.** Presence, connection and work, with one orbit per output batch | DNA-6 (A-07) |
| Work | **The active mission's lifecycle spine.** Where the work is, and whether it is moving | Proposed P-1; drawn from Core's existing states |
| World | **The constellation.** Your work's stable shape, with the thread drawn across it | DNA-5, Relations |

There is no central orb: an orb would be a fourth centre with no data behind it.

**The five-second picture.** A dark, still, aligned instrument of fine ink lines and quiet,
precise type. One point of light leaves a sentence, runs to a row, lands with a small ring, and
leaves a thin trace. Then nothing moves until Archeus acts again.

---

## C. Motion system

### C.1 Rules carried from V1 unchanged

- One motion registry (`tokens/motion.json`); nothing animates without an entry.
- The idle invariant: zero rAF callbacks and zero running animations at idle.
- Transform and opacity only; no `filter`, `backdrop-filter`, blend modes or animated paint
  properties.
- One parking rAF loop.
- Two clocks, `renderAt(t)`, no replay.
- Motion never carries meaning alone.

### C.2 The Visual Impact Ladder

There is one scale for intensity (VD §23; it supersedes VD §6.2's names). A screen has a ceiling
on the ladder as well as each event.

| Level | Name | When | Allowed | Budget |
|---|---|---|---|---|
| **L0** | **Calm** | No active work | Typography, alignment, surfaces, static marks | 0 frames |
| **L1** | **Ambient** | Something is true in the background | Static halos, the strip's state line, the mark at rest, residual thread traces | 0 frames; changes are one 160 ms step |
| **L2** | **Active** | Real work is producing | One row pulse per output batch (≤ 1 per 2 s per object); a travelling marker where the user is looking; the mark's orbit per batch (≤ 1 per 5 s) | Per event ≤ 240 ms (marker 600) |
| **L3** | **Significant** | A meaningful event or user transition | `morph` (object constancy); the focus plane; attention arrival; thread travel with landing; the causality path; spine stations advancing | Each ≤ 320 ms (travel 600 + landing 240; path ≤ 1.2 s) |
| **L4** | **Hero** | Rare, significant, gated (§K) | The handover reveal, plan arming, the resolution | ≤ 900 ms, skippable by any input, gated by significance and frequency |

- **Attention is a channel, not a level.** It rides L1 (the static band), L3 (one arrival) and
  the phone. It never reaches L4. If unresolved, it changes form rather than repeating.
- **Screen ceilings:**
  - Resources and Appearance: L2;
  - Attention: L3;
  - Conversation, Mission, Relations and Now: L3, plus their gated L4 moments.

### C.3 Durations and easing

| Class | ms | Easing | Use |
|---|---|---|---|
| `instant` | 0 | — | Selection, focus, hover on frequent controls; everything under reduced motion |
| `quick` | 160 | effects `cubic-bezier(.22,.8,.18,1)` | State change (A-01), peer fade (120), the state line |
| `standard` | 240 | effects | Pulse, arrival, landing ring, camera settle |
| `layer` | 220 / 280 | effects | Inspector, sheet, collapse |
| `morph` (new) | 320 | spatial: a `linear()` spring, ≤ 4 % overshoot | Object constancy (§C.5) |
| `travel` | 600 | linear | Thread head, marker |
| `orbit` | 900 | ease-in-out | The mark's orbit |
| `hero` (new, cap) | ≤ 900 total | composed of the above | L4 only |

**Duration philosophy:** the more frequent the motion, the shorter and subtler it is (E-50).
Effects (colour, opacity) never overshoot. Only `morph` may, by at most 4 %.

### C.4 Grammar

The axes have fixed meanings:

- **depth = focus;**
- **horizontal = lifecycle time** (the spine runs left to right; nothing moves left except
  "back");
- **vertical = priority.**

The categories — arrival, departure, expansion, collapse, transformation, progress, attention,
success, failure, waiting, reconnection and navigation — are specified in VD §6.1 with their
metaphor, duration, easing, direction, level and reduced-motion form.

### C.5 Object constancy

Choreography for one continuous environment (VD §6.4):

- row → mission;
- inspector → page;
- attention item → conversation turn;
- graph node → mission, through a DOM proxy;
- execution state → result, in place;
- command result → object.

Mechanism: same-document View Transitions, named by object id; React 19.3 `ViewTransition`.
**Gated on PR-2** (Qt frame time and tearing). Fallback: V1's cuts plus a 160 ms cross-fade.

### C.6 Fatigue rules

F-1…F-7 (VD §6.3):

- **F-1** — frequency demotes;
- **F-2** — significance promotes;
- **F-3** — first of the session, not first of all time;
- **F-4** — unresolved attention changes form;
- **F-5** — every motion is interruptible to its end state;
- **F-6** — the periphery gets only blink/pulse-class motion;
- **F-7** — the user sets the ceiling.

### C.7 Motion preference and reduced motion

`system | reduced` (V1, ADR-0044) gains **`quiet`** (V-D3, a design rule).

| Mode | What runs |
|---|---|
| `system` | Everything, up to the ladder |
| **`quiet`** | Everything except L4. Hero moments play at their L3 form (see §K for each one's quiet form) |
| `reduced` | No travel, no `morph`, no orbit, no focus-plane scale. State changes are instant or a ≤ 160 ms cross-fade. Static equivalents carry everything (V1) |

WCAG 2.2.2 is met by construction: nothing runs longer than 5 s.

---

## D. State visualization

**Rule: a state is a still picture; only a change of state moves.** Each state has three parts:

- a **rest picture** — figure, word and light level;
- an **entry signature** — at most one motion, once;
- a **continuing signal** — per real event only, never per tick.

**The light ladder:**

| Light | Meaning |
|---|---|
| **none** | nothing is happening, or it is history |
| **mark** | a state worth knowing |
| **halo** | live work is attached now |
| **event** | something just happened |

**Mapping from Core's presentation classes** (`tokens/presentation.json`). The full table, with
metaphors and evidence, is in VD §5.

| Class (glyph, role) | Rest picture | Light | Entry | Continuing |
|---|---|---|---|---|
| `planning` ◌ violet | ◌ + "Planning: …"; the spine at Plan | mark | — | each recorded plan step appears |
| `proposed` ○ text-2 | ○; the spine at Plan, with a dashed plan line | none | — | — |
| `needs_you` ◆ amber | ◆ + static band | mark | A-08 once | changes form (F-4) |
| `approved` ◇ text-2 | ◇ + "starts when …"; the Execute station armed | mark | thread → Execute station (L3, or L4 if significant) | — |
| `active` ● blue | ● + halo + liveness text | halo | the halo appears | a pulse per batch; a marker in focus |
| `verifying` / `reviewing` ● blue | ● at Verify / Review | halo | spine advance | as active |
| `blocked` ■ red | ■ + reason; the spine after it hollow | mark | A-01; the halo goes out | — |
| `paused` ‖ grey | ‖ | mark | A-01 | — |
| `failed` ✕ red | ✕ + reason + next actions | mark | A-01; the halo goes out; no shake, no flash | — |
| `done` ✓ green | ✓; the spine full; ink relaxes to secondary | mark → none | A-01, or resolution (L4) if significant | — |
| quiet (a reading, R P-3) | ● + halo + "no output for 12 min" | halo | — | none: pulses stop |
| offline | no halos + "as of hh:mm" | none | — | — |

**Precedence for aggregates** (the strip, mark, tray, phone badge, cluster summary):

> needs you > failed / blocked > unresponsive > active / verifying / reviewing > planning >
> approved > paused > done > neutral

This must be checked against ADR-0024's aggregation before it becomes a rule.

---

## E. Depth and material model

| Surfaces **may** | Surfaces **must not** |
|---|---|
| Sit at one of three opaque elevations, separated by lightness (an OKLCH ladder) | Blur, frost, refract or use `backdrop-filter` (the Qt readback; rulebook §24) |
| Carry a 1 px edge light (6 % raised, 9 % overlay) and a 1 px stroke | Use gradients as fills (the only gradient is the thread's travelling tail) |
| Cast a static ambient + key shadow (dark ≈ .24 / .28) | Animate `box-shadow`, `filter` or colour over large areas |
| Use concentric radii (inner = outer − padding) | Use parallax, tilt or perspective |
| Recede as the focus plane (scale 0.985 + `--scrim` 0.5) when a modal layer opens; `reduced` drops the scale, and HC / reduced transparency drop the scrim tint | Stack translucent layers, or put text over moving content |
| Cross-fade a pre-rendered hover shadow on conversation cards only | Light up on pointer movement |

**Per surface:** shell L1 · Now L1, with the focus plane for approvals · Conversation L1 ·
Mission L1, with the focus plane · Attention L1 · Relations: canvas alpha tiers plus L1 chrome ·
Resources and Appearance L0/L1 · Offline L0 · TUI L0.

3D (L4 spatial) is not part of the application (§R).

---

## F. Typography

| Role | V1 | V2 direction | Gate |
|---|---|---|---|
| `display` | 28/34 · 600 · Segoe UI Variable Text | **Candidate:** 32/38 · wght 560 · Display optical size (opsz 28–36) — the state sentence only | **V-D5: PR-4.** No global increase until readability and Qt rendering pass |
| `title-1` / `title-2` | 20/26, 16/22 · 600 | Unchanged sizes; weight 600 → 640 candidate | PR-4 |
| `body` / `body-strong` | 13/20 · 400 / 600 | 400 / **560** for row titles | PR-4 |
| `caption` | 12/16 | Unchanged; tertiary ink in the meta column | — |
| `mono` | Cascadia Mono 12/18 | Tabular numerals in the meta column, durations and counts | — |

**Constraints:**

- No web fonts (the offline rule).
- At most two families (Segoe UI Variable and Cascadia Mono; SF Pro and Roboto on phones).
- Weight and ink may carry state at rest — a done title relaxes to secondary ink and wght 450 —
  but never alone.
- Kinetic type is limited to one ≤ 160 ms step on a digit that changed because of an event. No
  scramble, no typewriter, no shimmer. The streamed message is the only kinetic text.
- Rem-based; layouts survive 200 %.

---

## G. Colour

- **Fixed state colours.** The six V1 colours stay fixed across themes:
  - active blue;
  - attention amber;
  - blocked/failed red, only when a person must resolve it;
  - paused grey;
  - thinking violet, for planning — never "AI thinking";
  - done green, after verification.
- **No new hue and no hue accent.**
- **Colour gets more expressive through light levels** (§D), not through more hues.
- **The thread is ink** (`thread`), or the user's thread tint (P22) — never a state colour. Its
  landing ring takes the same ink.
- **No colour animates continuously.** A state change cross-fades in 160 ms.
- **Authoring:** surfaces, inks and light levels are OKLCH ladders, generated into static tokens
  at build. There is no runtime `color-mix` animation.
- **High contrast and forced colours:**
  - halos become solid 1 px rings;
  - the state line becomes 2 px in a system colour;
  - the thread becomes 2 px `focus` ink;
  - the edge light and scrim tint are removed.

---

## H. Attention model

Obligation groups (R P-2). The grouping is client-side; acknowledge and snooze need Core records,
which require a Core ADR.

| Group | Contains | Glyph and colour | Visual distinction | Primary verb |
|---|---|---|---|---|
| **Decide** | Approvals, plan approvals, route decisions, questions Archeus asked | ◆ amber | The amber static band (≤ 12 %); top of every attention surface; ≤ 3 on Now | Approve / Answer |
| **Review** | Results awaiting the user's review; verification outcomes to accept | ◆ amber outline, or ✓ with "review" | No band; the thread trace from the result; the spine at Review | Accept / Request changes |
| **Unblock** | Blocked and failed work that needs a person (credentials, conflicts) | ■ / ✕ red | A red glyph and the reason first; no band, no pulse | Fix / Retry / Open |

**Shared rules:**

- Arrival animates once (A-08).
- Acknowledged is not resolved.
- Snooze wakes on a condition, never into an action.
- Unanswered items change form (F-4): they move up their group, then reach the phone (P20), then
  are named in the state sentence.
- Never more than three Decide rows on Now.
- The phone's Now is Decide plus summaries (R P-10).

---

## I. Mission lifecycle

**Understand · Plan · Approve · Execute · Verify · Review · Done** — the spine (R P-1). It is one
static, segmented figure reused on rows, cards, the inspector, the phone and the TUI.

**It needs no new Core data.** Each station is derived from Core's existing mission state and
presentation class:

| Station | Lit when (existing state) | Style (line vocabulary, R §7.3) |
|---|---|---|
| Understand | Mission exists; planning has not started or is asking a question | Solid once passed |
| Plan | `planning` / `proposed` | Filled while current; dashed if the plan is proposed but not approved |
| Approve | `needs_you` on a plan approval → `approved` | Filled amber while waiting; solid once approved |
| Execute | `active` | Filled blue, with the halo |
| Verify | `verifying` | Filled blue |
| Review | `reviewing`, or waiting on the user's review | Filled; amber if it waits on the user |
| Done | `done` (`failed` ends the spine in ✕ at the station reached) | Solid green ✓ |

**Additions:**

- **Not reached:** stations are hollow.
- **Blocked:** a station shows ■ and the segments after it hollow.
- **Rendering:** DOM/SVG, static, 0 frames.
- **Motion:** only the station change (A-01) and the thread's arrival at a station (§J).
- **Text equivalent:** "Step 4 of 7: Executing".
- **TUI:** `◌─●─◇─○` style, in ASCII-safe glyphs.

**Owed:** a mapping check against `state-machines.md`, so that every mission state lands on
exactly one station.

---

## J. The luminous thread

The detailed conceptual specification. Visual quality: VD §16.3. The grammar: VD §25.

### J.1 What a thread is

A thread is the visible record of **one Archeus-caused link** between two objects that Core
recorded: `Message.links`, a decision → mission, a plan → approval, an approval → execution, an
execution → resource or result, a cause → effect (after P21 Q-B1). **No thread is ever drawn
without such a record.**

### J.2 Its states

| State | Drawn as | When | Ends |
|---|---|---|---|
| **Travel** | Head + tail + line drawn on, 600 ms linear | The moment Core records the link and both ends are on screen | It lands |
| **Landing** | A ring at the target, scale 0.6 → 1 and fading, 240 ms | When the travel ends | Itself |
| **Lit path** | A static line at full ink | While the hop is the mission's *current* one (e.g. approval → Execute station, while armed) | When the next hop starts |
| **Residual trace** | The T2 rule on the target row; a faint static line in Relations | After landing | **On an event, never a timer:** acknowledgement, or the mission settling |
| **Dark** | Nothing | Future hops; history the user has acknowledged | — |

**Temporal fading is an event, not a clock.** No timer fades a trace, which keeps the idle
invariant. The trace leaves when the user acknowledges it or the work settles.

### J.3 The grammar across the lifecycle

| Hop | From → to | Where it is seen |
|---|---|---|
| Intent → plan | The user's turn → the plan card / spine Plan station | Conversation, Mission |
| Plan → approval | The plan → the Decide row | Conversation → Attention |
| Approval → execution | The decision → the spine's Execute station (**plan arming**, §K) | Mission, Now |
| Execution → resource | The execution → the harness/account/provider row it used | Mission, Resources (when on screen) |
| Execution → result | The execution → the result line | Mission, Conversation |
| Result → review | The result → the Review station / the Review row | Mission, Attention |
| Review → done | The spine → Done (**resolution**, §K) | Mission, Now |
| Cause → effect | Hop by hop along the recorded causal path | Relations (after P21) |

### J.4 Its rules

- **One travel at a time.** Surplus travels collapse into residual traces.
- **Intensity follows the ladder:**
  - a trace is L1;
  - a travel with landing is L3;
  - plan arming and resolution may be L4 (gated);
  - in `quiet` they play at L3, and in `reduced` the line simply appears.
- **Hover or focus on any thread part explains it** (proof of life, E-60): "Archeus approved
  *Deploy release notes* at 14:02 → started execution" — and a click opens the record.
- **Focus transitions:** when the user opens the target, the thread's landing point is the
  shared element of the `morph` (§C.5).
- **Mobile:** no cross-screen travels. The thread is the T2 rule plus a landing ring on the row
  the user sees. A push notification's open lands with the residual trace already present.
- **TUI:** the `│` rule (R13-16) plus the spine glyphs. No travel (the TUI has no motion).
- **Accessibility:** every travel has a polite live-region sentence ("Archeus updated …", V1).
  The thread is never the only carrier.

### J.5 Visual power without an arc reactor

An arc reactor is a *source* that is always on: its power is shown as potential. The thread
shows power as *consequence*: you watch your words become changes in the world, and the trail of
what Archeus did stays visible until you have seen it.

At world scale, the residual traces across the constellation draw **the day's light**: a true
picture of everything Archeus touched today. It is static, on demand, and different every day
because the work is different. That is the Archeus answer to the glowing core (VD §25.4) — and
it gets more striking the more Archeus actually does.

---

## K. Hero moments

Candidates under V-D4, all gated on PR-6. The full matrix, with frequency, emotion, intensity,
motion, sound-readiness and reduced motion, is VD §27.

| # | Moment | Gate (F-2) | L4 form (≤ 900 ms) | Quiet form | Reduced |
|---|---|---|---|---|---|
| K-1 | **Handover**: first open after ≥ 4 h | Once per absence | The state sentence, then the changed rows' traces appear in one stagger | Traces appear at once | Same |
| K-2 | **Plan arming**: the user approves a significant plan (≥ 3 tasks, or the mission's first approval) | Significance; F-1 demotes when there are more than 3 per 10 min | Commit → the thread runs from the decision to Execute → the station arms (◇) | Thread travel only (L3) | The station arms |
| K-3 | **Resolution**: a significant mission is Done *after verification* (≥ 10 min, or carried an approval) and is on screen | Significance; off-screen completions get V1's toast and the handover summary instead | Light runs back along the spine to Done; the halo releases; the result line appears | A-01 + result line | Instant |
| K-4 | **Causality path**: the user asks why | User-initiated | Light traverses the path hop by hop (≤ 1.2 s); the path stays lit | Same — it is L3 by nature | The path appears lit |

**Never hero:**

- failure (L3: the light goes out, the reason comes first);
- attention arrival (an alarm-fatigue risk);
- the emergency stop. The e-stop is immediate: every halo and trace drops to L0 in one 160 ms
  step. It is the one "power-down" moment, and it is true.

**Also at L3 (not hero):** the **first thread ever** plays a normal travel with a one-time caption
— "This line shows what Archeus changed" — that stays until dismissed. It teaches the signature
once (VD §27).

**Sound-ready:** each hero moment has a named sound slot, silent by default and not designed
here. Sound would come with the voice phase (§S Later).

---

## L. Relations

**The candidate signature place** (VD §11). It is the largest stage for the thread, not an
ornament.

- **Rendering:** 2D Canvas (V1). WebGL 2D (sigma-class) only on the measured trigger (R §5.2). No
  3D, shaders, parallax or 2.5D tilt.
- **What makes it Archeus's:**
  - a stable fingerprint (layout once, positions persistent);
  - the causality path as light (K-4);
  - mission origin threads;
  - static execution trails while live;
  - "since you looked" ink;
  - then-vs-now comparison instead of replay;
  - semantic zoom tiers;
  - focus neighbourhoods (ego graph at depth 1, alpha tiers plus thinner far strokes);
  - proof of life on every light.
- **Dependency:** the causality path, mission origin and execution-to-resource hops need P21's
  causality record (Q-B1) and activity record. **Until P21 lands, Relations V2 is limited to**
  the stable fingerprint, semantic zoom, the ego graph, then-vs-now, and proof of life on V1's
  existing lights.
- **Owed:** 60 fps at 1,000 nodes on integrated graphics (R13 §6); a real-corpus measurement.

---

## M. Mobile

- **Role:** the phone is the handover device (R P-10). Its Now is the state sentence, the state
  line, Decide rows, and per-mission summaries. Decisions happen there (rulebook §19).
- **Ladder ceiling L3,** plus K-1 and K-3 in their quiet form. No travel crosses the screen;
  the thread is the rule plus a landing ring.
- **No focus-plane scale on sheets** (the sheet itself is the focus); the scrim only.
- **Spine:** compact (7 dots + current label), drawn separately at the phone size, not scaled.
- **Targets ≥ 44 px.** Body 17. No motion during scroll. No hover-dependent explanation: proof of
  life is a tap, opening the record.
- **S-1 applies:** the approval card's task table becomes labelled rows.
- **The graph is hidden below 600 px; the list stands in for it** (V1, P18 A12).

---

## N. TUI

**What translates:**

- the state sentence (S-3 verbatim);
- the spine as glyphs;
- the `│` thread rule (R13-16);
- state glyphs and words (`presentation.json` ASCII fallbacks);
- the Attention groups as headings;
- the meta column as right-aligned fields;
- liveness as text.

**What does not:** any motion, travel, landing, `morph`, the focus plane, halos (shown as the
word "live"), hero moments, colour beyond the ANSI-derived state palette. The TUI is the ladder's
L0/L1 form of the same information — the proof that no meaning depends on motion.

---

## O. Offline

- Without Core, nothing is observed, so **nothing emits light**: no halos, travels, orbit or
  state-line colour.
- The view is a read-only snapshot with "as of hh:mm" in the meta column and the banner
  (rulebook, ADR-0044).
- The spine shows the last known station, outlined, with "as of".
- **Decide rows show, read-only, with no commands** (V1, R13-02).
- **On reconnect:** halos return in one 240 ms step; the strip says what changed; changed rows
  get residual traces. No celebration.

---

## P. Accessibility

| Area | Rule |
|---|---|
| Reduced motion | `reduced` mode (§C.7); every meaning has a static equivalent; `prefers-reduced-motion` honoured, plus the in-app preference |
| Quiet | `quiet` mode caps the ladder at L3 |
| Long motion | Nothing runs more than 5 s (WCAG 2.2.2), so no pause control is needed |
| Flashes | No flashes; no red flash ever (WCAG 2.3.1) |
| Vestibular | No parallax, tilt, zoom-on-scroll or sustained oscillation (≈ 0.2 Hz, E-39) |
| Contrast | 4.5:1 body, 3:1 state and secondary (V1 floors); the inks are checked on every elevation |
| High contrast / forced colours | §G mapping; figures render in system colours; the edge light and scrim tint are removed |
| Reduced transparency | The scrim becomes opaque; nothing is translucent anyway |
| Focus | 2 px thread ink + offset (ADR-0028); never removed; `morph` keeps focus on the shared element |
| Keyboard | Every action reachable; Enter / Ctrl+Enter / palette (R P-4); Alt+1/2/3/J (Q-A5) |
| Screen reader | The thread announces politely ("Archeus updated …"); attention arrival is assertive once; the spine has a text equivalent; the graph keeps its list mirror; liveness changes are announced ≤ 1 per 30 s |
| Touch | ≥ 44 px; no swipe that performs an action |
| Proof of life | Explanations are reachable by focus as well as hover |

---

## Q. Performance

**Measured baseline:** the SPA as built in the working tree is 145.7 KB gzip JS (478.6 KB raw),
5.9 KB gzip CSS and 0.9 KB appearance script (`archeus/api/static/assets`, measured 2026-10-04).

| Budget | Value | Gate |
|---|---|---|
| **Idle CPU / GPU** | 0 rAF callbacks, 0 running animations, no timers driving visuals | The V1 idle-invariant gate (unchanged) |
| **Frame rate during motion** | p95 ≤ 16.7 ms on integrated graphics in the Qt shell; no long task caused by motion | PR-1 / PR-2 measurement; a V2 perf test per new motion id |
| **Concurrency** | 1 thread travel; ≤ 8 markers; ≤ 12 pulses; 1 orbit (V1 caps) | Registry caps |
| **Bundle** | V2 visual work adds **≤ 10 KB gzip** in total over the measured baseline; any runtime dependency needs an entry in a budget file naming why | The bundle-budget gate proposed in R §9 (V2-U0) |
| **Memory** | The graph cap stays 500 drawn nodes; DPR ≤ 2; no retained offscreen canvases per row | V1 gates + a heap snapshot in PR-1 |
| **Mobile** | 60 fps on a mid-range phone for L2/L3 motion; no motion during scroll; no motion on a backgrounded page | A physical-phone measurement (owed since R13 §6) |
| **Qt shell** | Transform and opacity only; GPU compositing on; no blur or blend; WebGL 2 only for the escape hatch; nothing that needs WebGPU or SwiftShader (both compiled out, E-55) | The design gates + `test_gui_flicker`-style keyframe scan for the app CSS |
| **Graph** | 60 fps at 1,000 nodes on integrated graphics; layout once | Owed (R13 §6) |

---

## R. Technology policy

**The current stance** (VD §15; the main research §5):

1. **Native platform first:** CSS transitions and keyframes, WAAPI, View Transitions, `linear()`,
   variable-font axes, OKLCH-generated tokens.
2. **SVG and Canvas 2D where justified:** SVG for the thread, spine and rings; Canvas 2D for the
   constellation (V1's one parking loop).
3. **No animation runtime dependency by default.**
   - Anime.js, GSAP, Motion, Lottie, dotLottie and Rive are rejected.
   - Motion `LazyMotion` (7.4 KB) may be reconsidered only if View Transitions fail PR-2 and
     layout animation is still wanted.
4. **No three.js in the application.** Only the V1.x-3D research spike, with kill criteria, may
   use it. The website keeps its scene.
5. **No WebGPU dependency.** It is compiled out of Qt 6.11 and not Baseline.
6. **No CDN runtime dependencies.** Everything ships in the wheel; any WASM or font must be
   self-hosted. Nothing is fetched at runtime.
7. **No decorative GPU-heavy background.** No stage, light field, particle field or bloom.
8. **Prototypes add no production dependency.** A prototype that needs a library to *measure* a
   hypothesis keeps it in a scratch project outside the shipped client.
9. **Figma Motion is a design tool, not a runtime.** Its exported CSS is a draft, re-checked
   against the registry rules.

---

## S. V1 / V2 boundary

### V1 — shipped, plus the R13 corrections and the decided follow-up (before P26)

- **As built through P19, with R13 passed:**
  - the quiet-instrument language;
  - the registry (16 entries, 15 built);
  - the thread as T1/T2;
  - the halo, pulse, marker and orbit;
  - Canvas 2D with mirror;
  - ADR-0014 IA;
  - Appearance (ADR-0044);
  - the offline snapshot;
  - the TUI.
- **Decided follow-up, not yet built:**
  - R13 §8: R13-03, 05, 08, 11, 12, 15, 16;
  - **S-1, S-2, S-3** (rulebook §46.4);
  - Q-A5 (Alt keys) before P26.
- **Still owned by V1 phases:**
  - P20: push, credentials;
  - P21: activity chip A-17, trace, causality Q-B1, server search, schedules, live_work;
  - P22: thread tints, people nodes, Resources UI;
  - P23: device evidence;
  - P25: the site;
  - V1.x: compact density.

### V1.x — research only

- The **V1.x-3D renderer spike**, with kill criteria (R §5.2).
- The **prototypes PR-1…PR-6** (§T).
- The owed V1 measurements: 60 fps at 1,000 nodes on integrated graphics; a physical phone.
- A real-corpus graph measurement.
- None of these ships product UI.

### V2 — this architecture

The Visual Impact Ladder, the motion system v2 (`morph`, `quiet`, fatigue rules, object
constancy), state visualization and precedence, the depth/material model, typography (subject to
PR-4), colour authoring, the Attention groups (with the Core ADR for acknowledge and snooze), the
lifecycle spine, the luminous thread grammar, the hero moments (subject to PR-6), Relations V2
(full form after P21), the mobile handover role, the TUI translation, and offline behaviour.
V2-U0…U6 (R §12; the additions in VD §18.2).

### Later

- **Voice:** V2-A0…A5 (ADR-0050). Its visual extension is VD §29: real mic and output levels,
  push-to-talk, captions first.
- **Sound for the hero slots.**
- **OS-level presence:** the taskbar and tray overlay in the state colour (feasibility
  unverified in Qt 6).
- **The week's retrospective constellation.**
- **XR and advanced spatial experiences:** only if a future evidence-based spike passes.
- **3D in the app:** only if the V1.x-3D spike passes its kill criteria.

---

## T. Decisions, gates and the next phase

**Recorded (the user, 2026-10-04; rulebook §46.4):**

- S-1, S-2, S-3: V1 corrections.
- V-D1: yes — §27 clarified.
- V-D2: yes.
- V-D3: yes, as a design rule.
- V-D4: yes, prototype-gated.
- V-D5: yes, prototype-gated.

**Mandatory prototype gate** (before any production V2 visual implementation). Each prototype:

- implements only enough to measure its hypothesis;
- is tested in the Qt shell, on the desktop browser, on a phone where relevant, under reduced
  motion and under high contrast;
- measures performance;
- records subjective visual quality and repetition/fatigue;
- ends in a written pass/stop decision.

| Id | Hypothesis | Pass | Stop |
|---|---|---|---|
| PR-1 | The thread's light quality holds in Qt | p95 ≤ 16.7 ms during travel on integrated graphics; no tearing; idle invariant holds; HC/reduced forms correct | Tearing or p95 > 20 ms → keep V1's thread |
| PR-2 | View Transitions work for object constancy in Qt 6.11 | p95 ≤ 16.7 ms; no flash or tearing; reduced motion respected; focus kept | Fails → V1 cuts + 160 ms cross-fade |
| PR-3 | The focus plane helps without discomfort | No discomfort reported; the base stays legible under the scrim | → scrim only |
| PR-4 | Segoe UI Variable optical size and weights render in Qt, the browser and HC; a 32 px display reads better | opsz visibly applied; no layout shift at 200 %; readability check passes | → keep 28/34 at 600 |
| PR-5 | The state pictures are identifiable without colour at 12/16/20 px | The user identifies every state | Redraw |
| PR-6 | The four hero moments survive daily use | After a two-week dogfood with F-1/F-2 thresholds logged locally, the user still wants each one | A moment turned off → demoted to L3 |

**Undecided:**

- the state precedence vs ADR-0024 aggregation (§D);
- the flow strip vs "spatial primary" (ADR-0027, R §8.3);
- E-stop placement (R P-13);
- Q-V6, Q-C1, Q-C2 (rulebook §46);
- the Attention acknowledge/snooze Core records (a Core ADR);
- OS-level presence feasibility.

**The next phase.** Not V2 production UI. In order:

1. Finish V1 through P20–P26, including the S-1/S-2/S-3 and R13 §8 follow-up.
2. In parallel and without touching product code, **V2-U0 Evidence**:
   - the owed V1 measurements;
   - the bundle-budget gate;
   - the prototypes PR-1…PR-6 in a scratch harness;
   - the ADRs listed in VD §18.4 ("Light is evidence", "Intensity and fatigue", "Object
     constancy");
   - the state-picture catalogue and motion registry v2 documents.
3. Only after those pass and are approved: V2-U1 Foundation.

---

## U. JARVIS differentiation matrix

Filled from the benchmark (VD §20–§22; E-67…E-73). The "typical JARVIS" column is what the 13
public repositories and five reels actually do, with counts out of 13 where measured.

| Capability | Typical JARVIS implementation (evidence) | Archeus approach |
|---|---|---|
| **Central visual** | An orb or arc reactor (12/13; 4/5 reels); no data behind it beyond a state colour or spin speed | **No orb.** The work at three scales: the mark (system), the active spine (work), the constellation (world), plus the thread between them (§B) |
| **Activity** | A perpetual render loop while visible (13/13); 10/13 never pause; spin speed as the state signal (kvdoe ×3.5) | Real work only: a pulse per batch, a marker per batch, an orbit per batch; 0 frames at idle (§C) |
| **Telemetry** | Fabricated live values in 8/13 ("1.21 GW", random battery, hex streams); real CPU/RAM in 7 | Only Core's state: missions, needs-you, output age, attempts, cost — every number answers "why" (V-1) |
| **3D** | 7/13 WebGL scenes, particles 220–3,000; the legacy Archeus collapse (E-38) | Selective and evidence-based: 2D constellation; WebGL 2D only on a measured trigger; 3D only via the V1.x spike (§R) |
| **Light** | Neon glow by stacked `box-shadow`/`blur` (Dix01: 62 + 58 + 31 backdrop); cyan on black (11/13) | The functional luminous thread — the brightest thing in the product, and only when Archeus acts (§J) |
| **Motion** | Constant; infinite CSS animations in 12/13 (up to 16 + ~25) | Event-driven, on the Visual Impact Ladder; L4 a few times a day (§C.2) |
| **Voice** | An orb or waveform; real audio in 8/13; `Math.random` or sine in the rest | Later (V2-A1): a level meter from real mic and output RMS only while active; captions first; barge-in stops at once (VD §29) |
| **Navigation** | Floating, draggable HUD panels (Dix01, nikdonthala); overlap through translucency | Persistent objects that transform into their detail (`morph`); opaque focus planes (§C.5, §E) |
| **Completion** | Glow or burst, or nothing | Meaningful resolution after verification: light returns along the spine to Done, the result first (K-3) |
| **Graph** | A decorative globe or "brain" (shaurya, xxjun; reel 5's "neurons firing") | Causal Relations: a stable fingerprint, the causality path as light, proof of life (§L) |
| **Boot** | A fake kernel log or intro (5/13) | Handover: the real state sentence and what changed (K-1) |
| **Mobile** | Secondary: responsive in 5 of 11 web UIs | First-class: the phone is the handover and approval device (§M) |
| **Offline** | Absent | A real read-only snapshot with "as of" and no false light (§O) |
| **Accessibility** | Reduced motion detected in 5/13 and honoured by the renderer in 1/13; aria from 0 to 43 | A core requirement: reduced and quiet modes, static equivalents for everything, gated (§P) |
| **Typography** | Orbitron/Rajdhani in 8/13; Courier New | Segoe UI Variable (optical sizes, precise weights) and Cascadia Mono; no display web font (§F) |
| **Performance** | Measured audio stalls from a full-screen HUD (hasibjaan ~24 ms/frame); `shadowBlur` 40×DPR per frame | Idle 0 frames; p95 ≤ 16.7 ms in Qt on integrated graphics; a bundle budget (§Q) |
| **Security** | `CORS(*)` beside terminal and file endpoints (PRUTU29) | Loopback guard, per-run token, validated parameters (existing) |

**What Archeus keeps from JARVIS, deliberately:**

- **presence** — the mark;
- **named states** — the presentation classes, reel 3;
- **a distinct tool/action state** — P21 action kinds, eadmin2;
- **real reactivity** — Live Wire;
- **a typed state → visual table** — `presentation.json`, bertrand;
- **cinematic change** — §C.5, §K;
- **a recognisable signature** — the thread.

## V. The "more compelling than JARVIS" test

The success criteria, defined before any implementation so V2 can be judged against them. Run at
V2-U0 on the prototypes, and again before V2 ships.

- **The comparison set:** Archeus V2 prototype clips/stills against three references — two
  JARVIS-style projects from E-67 (one premium, thisisreyy; one typical, Dix01) and the V1 Archeus
  build.
- **Participants:** the user plus at least four people who have not built Archeus.

| Criterion | Test | Pass |
|---|---|---|
| **Immediate recognition** | 5-second exposure to an unlabelled Archeus still and clip, mixed with the comparison set, then a second, different Archeus screen | ≥ 4 of 5 participants match the two Archeus screens as the same product, and name a distinguishing element (the expected answer is the thread, or "still with one light") |
| **Visual hierarchy** | 5 s on Now (desktop and phone), then four questions: what is Archeus doing; what needs you; what changed; what can you do next | ≥ 90 % correct, on the default, `reduced` and high-contrast renderings alike |
| **Emotional impact** | 7-point semantic differential on six scales — sophisticated, powerful, alive, calm, trustworthy, futuristic — after 2 minutes with each item in the comparison set | Archeus ≥ the JARVIS references on *sophisticated, trustworthy, calm*; within 0.5 of the best JARVIS score on *powerful, alive, futuristic*; and ≥ 5.0 on all six |
| **Repetition** | PR-6 dogfood: two weeks of daily use with the motion moments logged locally | The user keeps every L4 moment enabled, turns none off, and reports no moment as tiresome |
| **Performance** | The Qt shell on integrated graphics; a mid-range phone; offline; 1,000 nodes | Idle 0 frames; p95 ≤ 16.7 ms during motion; no tearing; 60 fps at 1,000 nodes; offline shows no false light |
| **Accessibility** | The hierarchy test repeated under `reduced` and forced colours; axe on every V2 surface; keyboard-only completion of approve, steer and open-why | Hierarchy accuracy within 5 points of the default; 0 axe violations; every task completed by keyboard |
| **Credibility** | Each participant is asked which product they would trust to act on their code | Archeus chosen by ≥ 4 of 5 |

**The target, restated:** more emotionally compelling than typical JARVIS interfaces, and
substantially more usable and credible as a real product. A V2 build that wins on *calm* and
*trustworthy* but loses on *alive* and *powerful* has not met the bar; nor has one that wins
*futuristic* and loses *trustworthy*.
