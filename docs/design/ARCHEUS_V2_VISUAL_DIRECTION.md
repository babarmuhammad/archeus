# Archeus V2: Visual Impact and Direction

**Addendum to [ARCHEUS_V2_UI_RESEARCH.md](ARCHEUS_V2_UI_RESEARCH.md).**

**Status: RESEARCH — PROPOSED, with five direction decisions RECORDED.** The user decided V-D1 to
V-D5 on 2026-10-04 (rulebook §46.4; §30 below). V-D4 and V-D5 are prototype-gated. Every other
recommendation is a proposal for the user to decide on. The governing V2 document is now
[ARCHEUS_V2_UI_ARCHITECTURE.md](ARCHEUS_V2_UI_ARCHITECTURE.md). Apart from the §27 clarification
that V-D1 required, nothing here amends the V1 rulebook
([ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md](ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md)),
an ADR, a gate or a V1 phase. Where this document proposes to change a V1 rule, it says so and
names the amendment that change would need. "Do not proceed on inferred approval" (rulebook §0,
R5) applies.

Date 2026-10-04. Branch `archeus-v1-rearchitecture` at `cb11480`. Nothing in the product, the
tests, CI or the dependencies was changed to produce this. The evidence lives in §6 of
[../research/2026-10-v2-ui-reference-study.md](../research/2026-10-v2-ui-reference-study.md),
cited here as `E-n` (E-1…E-37 from the first pass, E-38…E-66 from this one). This document is
meant to be readable without it.

**Tags.** **[A]** an Archeus fact (code, a decided document, the legacy record). **[R]** a
research fact (E-n). **[I]** inference or recommendation.

## Contents

1. The answer first
2. What Archeus already learned about spectacle
3. Visual Inspiration Atlas (deliverable 1)
4. Depth and material strategy (deliverable 4)
5. Living state visualization (deliverable 5)
6. Motion language: grammar, intensity, fatigue, choreography (deliverable 3)
7. Hero moment map (deliverable 7)
8. Ambient visualization (deliverable 8)
9. Typography and colour direction (deliverable 9)
10. Hero surfaces and the V2 Wow Map (deliverable 2)
11. Spatial Relations as the signature place (deliverable 6)
12. Emotional design
13. Wow or gimmick: classification of every technique
14. Anti-patterns and gimmicks to reject (deliverable 12)
15. Technology comparison for visual effects (deliverable 11)
16. Visual signature candidates and the recommendation (deliverable 10)
17. The smallest set of principles: the foundation for V2 visual architecture
18. What this changes in the V2 research, the roadmap and the next documents
19. Method and gaps

**Part II — benchmark against JARVIS-style interfaces**

20. JARVIS / REEL VISUAL BENCHMARK
21. What JARVIS gets right and wrong — the reel/everyday gap
22. More impressive than a JARVIS HUD without being one
23. The Visual Impact Ladder
24. Cinematic without clutter
25. The luminous thread as an Archeus-wide grammar
26. "Archeus Core" — the centre of gravity, without a fake core
27. The Archeus Hero Moment Matrix
28. The "alive" feeling, from real state only
29. Voice as a future visual extension
30. Decisions recorded and what Part II changes

---

## 1. The answer first

**The question.** How can Archeus become visually captivating, emotionally distinctive and
breathtaking to use, while remaining a serious system interface?

**The verdict.** Archeus can become dramatically more beautiful and more recognisable. The
evidence does not support getting there by making the interface spectacular everywhere, and
Archeus has its own proof of that. The legacy GUI built the spectacular version:

- a bloom-lit WebGL stage;
- 26 generative canvases;
- loud skins and themed worlds;
- a lit 3D cluster;
- particle bursts.

Its users rejected each of these: "overstimulating", "da buttare", "everything else is worse"
(E-38). External products that stay beautiful in daily use point the same way:

- Linear grows calmer every year (E-61);
- Flighty aims to be "boringly obvious" and "shine when things go awry" (E-63);
- GitHub had to add "proof of life" to its globe so the arcs were not "just design animations"
  (E-60);
- Arc paid a "novelty tax" (E-65);
- Apple's Liquid Glass was called "spectacle over usability" and gained a Tinted switch within
  four months (E-40).

**What the research supports** is a product that is exquisite everywhere, alive exactly where
work is happening, and spectacular only at a few moments it has earned. The five sources of that
beauty, each tied to something Archeus already is:

1. **Light that is evidence.** In Archeus only work emits light, and light travels only along the
   path the work actually took: from the sentence Archeus said, to the object it changed, through
   the mission's lifecycle. This is V1's thread (DNA-1) given proper light quality, a landing and
   a grammar. **It is the recommended visual signature** (§16).
2. **Stillness as the canvas.** At idle nothing moves. The beauty at rest comes from type,
   alignment, tonal depth and fine line (Huw Prosser E-1, Linear E-61) — the parts a viewer feels
   "after a few minutes of using the app".
3. **Depth that means focus.** Opaque planes rather than glass. The object you work on comes
   forward and everything else recedes. Built from tonal elevation, edge light and transform —
   never blur (E-39, E-41, E-42).
4. **Objects that persist.** A row becomes the mission and a node becomes the mission. An
   attention item becomes the conversation turn that answers it. Nothing vanishes and reappears
   elsewhere, so Archeus reads as one continuous environment instead of pages (E-42 container
   transform, E-43 Live Activities). Same-document View Transitions do this at 0 KB.
5. **Intensity that is earned and budgeted.** Five intensity levels (ambient, normal, focus,
   attention, hero). Each moment's intensity is proportional to its significance and inversely
   proportional to how often it happens. Unresolved attention changes form rather than repeating
   (E-49, E-50).

**Cost of the whole direction:**

- **No new runtime dependency.** Every technique here is CSS, WAAPI, SVG, Canvas 2D or View
  Transitions, all available in Chromium 140 / Qt 6.11 (E-56).
- **No 3D, no WebGL, no blur in the app.**
- **About a dozen new tokens.**
- **Rule changes:** two V1 rule wordings need user decisions (§18.1). Everything else extends V1
  rather than contradicting it.

**What someone should recognise in five seconds without the logo:** a dark, still, precisely
aligned instrument of fine ink lines and quiet type. Then one point of light runs from a sentence
to the thing it changed, lands, and leaves a mark — and everything is still again.

---

## 2. What Archeus already learned about spectacle

The strongest evidence in this study is internal (E-38). The legacy GUI is the same product with
the same users, and it made four separate attempts at visual spectacle:

| Attempt | Result | Lesson [I] |
|---|---|---|
| WebGL stage with bloom behind the whole app | "overstimulating, confonde"; users switched to the skin with no background | An always-on field competes with the content, whatever its beauty |
| 26 generative canvases in rows, gauges, nav | Deleted for "smearing motion through the content" | Motion that is not news is noise |
| Quiet motion at 16 % opacity behind cards | Invisible, so it did nothing | The middle ground fails both ways; motion must be in the foreground and mean something, or be absent |
| Loud skins and worlds | "da buttare"; "Terminal won because its transformation is in the chrome and its background is quiet" | **Drama belongs in the interface, not the wallpaper** |
| Lit 3D PBR cluster | "everything else is worse"; "just remove the 3d part"; and a 249.9 ms p95 frame collapse in the Qt shell | The beauty was in the structure (populations, fine lines), not in the 3D lighting |
| Particle bursts | Survived only as one-shot effects of ≤ 1.6 s on a real event | One burst on a real event is feedback; anything continuous is wallpaper |

What survived every round, and what V1 then carried forward, is **light that reports real state**
(halo, pulse, travelling marker, the thread). V2's visual direction should start from that
record, not from a mood board.

---

## 3. Visual Inspiration Atlas

Each reference answers the brief's six questions in short form:

- **Impact:** what creates the visual impact.
- **Emotion:** what creates the emotional response.
- **Functional / Decorative:** which parts do work and which are ornament.
- **Annoying in an app:** what would wear thin in daily use.
- **Archeus adapts:** what Archeus could take.

**Class** uses §13's scale: **Pr** productive, **Em** emotional, **Am** ambient, **De** decorative,
**Gi** gimmick.

| Reference | Impact | Emotion | Functional | Decorative | Annoying in an app | Archeus adapts | Class |
|---|---|---|---|---|---|---|---|
| **visionOS** (E-39) | Planes at different depths; a sheet pushes its window back | Calm focus, a sense of place | Depth = hierarchy; three ink levels; hover only on targets | Specular glass | Constant refocusing between depths | Focus plane recession (§4); three ink levels; "small amounts of depth" | Pr |
| **Liquid Glass** (E-40) | Lensing, morphing controls | Novelty, physicality | A distinct control layer; concentric radii | Refraction, wobble | Legibility ("text on top of text"); "motion without meaning" | Control layer, concentric radii, adaptive shadow — **not** the glass | Pr / Gi |
| **Fluent 2 / Windows 11** (E-41) | Mica's quiet tint; layering with strokes | Native, settled | Base + content layers; strokes, not key shadows; quick fade between top-level pages | Acrylic | Acrylic is GPU-heavy and off on battery | Opaque layering, 1 px strokes, dark shadow tokens; quick fade for peer navigation | Pr |
| **Material 3 Expressive** (E-42) | Spring physics; container transform | Liveliness | Spatial vs effects split; container transform | Expressive overshoot | Bounce on every tap | Container transform; standard (low-bounce) springs only | Pr |
| **IBM Carbon** (E-42) | Restraint | Trust | Productive vs expressive modes | — | — | The intensity split behind §6.2 | Pr |
| **Dynamic Island / Live Activities** (E-43) | A compact object grows into detail | Continuity, "it's handled" | Same anchors across sizes; ≤ 2 s; update only on new content | — | Alerts for non-essential updates | Object constancy (§6.4); "update only when the content changed" | Pr |
| **Stripe globe** (E-59) | Scale, twinkle, arcs | Awe, invitation to explore | Real coverage; static fallback; pause on scroll | Twinkle, aurora | Jank on mid laptops; it is a homepage, seen once | A single hero, hard fps rule, static first paint — on the **site** only | De (in an app) |
| **GitHub globe** (E-60) | Real PRs arcing across the planet | Wonder at real activity | **Proof of life**: every arc hoverable and clickable; quality tiers on measured fps | Halo, rotation | 40–55 % CPU without GPU | **Every light can be asked why**; the landing ring; measured-fps tiers | Pr (the proof-of-life rule) |
| **Linear** (E-61) | Alignment, density, neutral chrome | Control, quality "felt after a few minutes" | "Don't compete for attention you haven't earned"; "structure felt, not seen" | — | — | Felt structure, contrast-generated themes, dimmed chrome | Pr |
| **Awwwards SOTY** (Igloo, Lusion…) (E-62) | Scroll-driven camera, shader fields, scrambled type | Cinema, spectacle | Almost none — single-visit storytelling | Nearly all of it | All of it, by the second visit | Baking heavy work offline; nothing visual | Gi (in an app) |
| **Flighty** (E-63) | Departure-board calm; reason-first alerts | Reassurance, then warmth | One line per flight; the reason first; minimal view while nothing changes | Passport artwork (rare, earned) | — | Calm until something changes; reason first; a rare retrospective of your own work | Pr / Em |
| **Wattenberger repo-vis** (E-64) | A fingerprint of your own code | Recognition, ownership | Learned by repetition; regenerated; links on hover | Colour by type | — | The constellation as a stable fingerprint (§11) | Pr / Em |
| **Gource** (E-64) | History growing as a tree | Nostalgia, scale | An artefact, not a view | The replay | As an always-on view: all of it | A rare retrospective, not a live surface (V1's "no replay" holds) | Em |
| **Arc** (E-65) | Colourful spaces, novelty | Delight, then fatigue | Few features used (0.4–5.5 %) | Most of the novelty | The "novelty tax" | Don't make users learn decoration | — (warning) |
| **Things 3** (E-65) | Magic Plus drag; haptics | Playfulness that does work | The gesture's drop point decides where the item goes | Bounce | — | Delight only where the gesture does real work | Pr / Em |
| **(Not Boring) Habits** (E-65) | Explosive 3D checkbox, sound | Celebration | Long press makes it intentional | The explosion | Would be, if frequent; it fires about once per habit per day | Intentional, rare emotional moments; ordinary controls stay ordinary | Em |
| **Raycast confetti** (E-65) | Confetti on command | Fun | Doubles as a success signal | The confetti | "Steals focus" | — (an Archeus success signal must never take focus) | Gi |
| **Vercel Ship / Next.js Conf** (E-66) | One shader hero; everything else plain | Event energy | Adaptive quality from measured fps | The hero | Ferrofluid triggered trypophobia; oil-slick "too loud" | Concentrate any spectacle in one place; pull back to "darker, sleeker… grounded" | De (site) |
| **Siri glow / Gemini waveform** (E-44) | Light that responds to your voice | Being heard | Driven by real signal | Siri's ring | — | Light driven by real signal (V2-A1's mic meter, main doc §5.4) | Pr |
| **Shimmer text, spinner verbs** (E-44) | Loops of fake activity | Unease, "meaningless word" | None | All | Users ask to remove them | Nothing | Gi |
| **Perplexity steps** (E-44) | A plan visibly advancing | Patience, trust | Intermediate progress makes waits acceptable | — | — | The lifecycle spine, planning steps as they are recorded | Pr |
| **Ableton clip launch** (E-46) | A blinking clip waiting for the bar | "Committed, about to happen" | Blink = queued for a known boundary | — | A blink over a long wait | The metaphor of "armed" (approved, starts at X) — without the blink | Pr |
| **Live Wire** (E-48) | A string whirling with network traffic | Peripheral awareness | Motion proportional to real signal | — | A fast spin while you work | Proportionality: no event, no motion | Am |
| **Windows taskbar / macOS dock** (E-45) | Colour and bounce on the icon | Glanceable status | Precedence (error > paused > normal); bounce scaled by severity | — | Critical bounce left on | State precedence; persistence scaled by severity | Am |
| **Huw Prosser** (E-1) | Monospace grid; tabular meta | Craft, confidence | Alignment, hierarchy by weight | — | — | The meta column; type as structure | Pr |
| **Thinking Orbs** (E-2) | Per-state living figures | Charm | A state vocabulary | Perpetual loops | Loops at idle | Static state figures (main doc §7.5) | De / Gi |
| **Obsidian graph** (E-30) | Your notes as a galaxy | Identity, pride | Little ("never found it helpful") | Mostly | Hairball | Recognition without the hairball: an ego graph and stable layout (§11) | Em / De |

**Pattern across the atlas [I].** Every reference that stays beautiful in daily use draws its
impact from **the user's own data made legible** (GitHub, Flighty, repo-vis, Perplexity), or from
**craft at rest** (Linear, Huw Prosser, Fluent). Every reference that is breathtaking once draws
its impact from spectacle that is unrelated to the user's data (Awwwards, Stripe's twinkle,
shimmer), and it either lives on a marketing page or gets dialled back.

---

## 4. Depth and material strategy

The brief's five-level progression, judged against Archeus's constraints: the Qt shell has no
blur and no blend modes (rulebook §24, E-38); there is no WebGPU and no software WebGL there
(E-55); and vestibular dysfunction affects 35 % of adults over 40 (E-51).

| Level | Technique | Value for Archeus | Cost and risk | Verdict |
|---|---|---|---|---|
| **0 — Flat** | V1's surface-1 base with hairlines | Dense lists, forms, the TUI | None | **Keep** for base lists and forms |
| **1 — Layered** | Tonal elevation (lighter surface = higher), 1 px strokes, dark-tuned ambient shadows, concentric radii, a 1 px **edge light** on the top inner edge of raised and overlay surfaces | Makes the hierarchy feel crafted; the dark UI gains depth without effects (E-41, E-42) | Static, 0 frames. Shadows are never animated; a pre-rendered shadow layer is cross-faded by opacity (E-58) | **Adopt — V2 Core foundation** |
| **2 — Material** | Translucency, blur, vibrancy, adaptive light | Translucency/blur: the readback that tears Qt (§24); Microsoft limits Acrylic to transient surfaces and turns it off on battery (E-41); Liquid Glass's legibility backlash (E-40) | High | **Reject blur and glass. Adapt vibrancy** as three ink levels (primary, secondary, tertiary). **Adapt "Smoke"** as an opaque-colour scrim faded by opacity under modal layers. Adaptive light only through the thread (§5) |
| **3 — Dimensional** | Subtle perspective, parallax, depth transforms | One real use: the **focus plane** (visionOS "recedes along the z-axis", E-39). When an approval, dialog or the inspector-as-page opens, the base plane scales to 0.985 and its scrim rises to 0.5 | Transform/opacity only. Parallax and perspective tilt are vestibular risks (E-51) and the most distracting motion type at the edge of vision (E-49) | **Adopt the focus plane only** (V2-U2). **Reject parallax and tilt** |
| **4 — Spatial** | Real 3D / WebGL | No comprehension gain for graphs (E-8); the legacy frame collapse (E-38); WebGL 2 only in the shell, with no software fallback (E-55) | High, permanent | **Reject in the app.** The website keeps its 3D journey scene as the brand's spectacle. The V1.x-3D research spike stays as the main doc §5.2 scopes it |

**Depth tokens proposed (new, all static):**

| Token | Dark | Purpose |
|---|---|---|
| `--surface-1/2/3` | unchanged values, re-derived in OKLCH as an even lightness ladder | Elevation by lightness (E-42) |
| `--edge-light` | `text` at 6 % on the top inner edge (raised), 9 % (overlay) | Light from above without a gradient fill |
| `--shadow-raised` / `--shadow-overlay` | ambient + key, opacities ≈ .24 / .28 (Fluent dark, E-41) | Shadow as a static layer |
| `--scrim` | `bg` at 0.5, opaque colour, opacity-faded | Focus plane, modal layers |
| `--recede-scale` | 0.985 | Focus plane (0 under reduced motion) |
| `--radius-concentric` | inner = outer − padding | Nested surfaces read as one object (E-40) |

**Per surface:** shell L1 · Now L1, with L3 when an approval opens · Conversation L1 · Mission L1/L3 ·
Attention L1 · Relations: canvas depth tiers (V1 alpha by hop) plus L1 chrome · Resources and
Appearance L0/L1 · Offline L0 (no light at all; §5) · TUI L0.

---

## 5. Living state visualization

**The question.** Should Archeus have a coherent visual language for the states Core can be in?
**Yes** — and the evidence decides what it is made of.

**The evidence:**

- Real-signal indicators are trusted, and canned loops are criticised (E-44: Gemini's waveform
  versus shimmer and random spinner verbs).
- Peripheral motion is detected far better than colour, but travelling motion is the most
  distracting kind and a slow blink the least (E-49).
- An auto-playing loop longer than 5 s beside content needs a stop control (WCAG 2.2.2, E-51).
- Showing progress steps makes people willing to wait (Perplexity, E-44).
- A shipped precedence rule exists for status (Windows taskbar, E-45).

**The principle: a state is a still picture; only a change of state moves.** Every state has
three parts, and motion appears only in the second:

1. a **rest picture** — a static figure, a word, and a light level;
2. an **entry signature** — at most one motion, played once, when Core records the change;
3. a **continuing signal** — motion only per real event (an output batch), never per tick.

**The light ladder.** How much light an object gives off is itself the state encoding:

| Light | Meaning | Drawn as |
|---|---|---|
| **none** | nothing is happening, or it is history | Neutral ink |
| **mark** | a state worth knowing | State glyph and colour |
| **halo** | live work is attached to this object now | Static ring (V1 A-03) |
| **event** | something just happened | One pulse, a travelling marker, or the thread (V1 A-02/04/05) |

**The states.** "Metaphor" is what the research supports. The rest picture and entry signature
are proposals for the state-picture catalogue (§18.3), not final animations, as the brief asks.

| State (V1 class) | Metaphor the research supports | Rest picture | Entry signature (once) | Continuing signal | Reduced motion | Text |
|---|---|---|---|---|---|---|
| **Thinking / planning** (`planning` ◌ violet) | *Structured emergence*: the plan appearing step by step as Core records it (Perplexity, E-44) — not "thought" | ◌ + "Planning: <what>"; the spine's Plan station current | none | each recorded plan step appears in the spine (a real event) | appears at once | "Planning: 3 of ? steps" |
| **Searching / reading / editing** (P21 action kind) | *What it is doing now*, only when recorded | 12 px action figure beside the activity line (main doc §7.5) | A-01 cross-fade when the recorded action changes | none between records | instant | "Searching code" |
| **Approved, waiting to start** (`approved` ◇) | *Armed*: committed, waiting for a known boundary (Ableton, E-46) | ◇ + "starts when X"; the spine's Execute station outlined | the thread draws from the decision to the Execute station (§7) | none — no blink over a long wait (E-51) | the station outlines at once | "Approved · starts after the current task" |
| **Asking / needs you** (`needs_you` ◆ amber) | *Focused attention*, top of the precedence | ◆ + static attention band | A-08 arrival once | **changes form, never repeats** (§6.3, F-4) | band only | announced once |
| **Executing** (`active` ●) | *Directional flow* — the light moves the way the work goes | ● + halo + liveness text | the halo appears (static) | one row pulse per output batch at the edge of vision; a travelling marker only where the user is looking (graph, mission view) — E-49 | static live edge | "output 4 s ago" |
| **Quiet** (new reading, main doc P-3) | *Silence is shown by stillness* (Live Wire's "small twitch every few seconds", E-48) | ● + halo + "no output for 12 min" | none — pulses simply stop | none | same | the age |
| **Blocked** (`blocked` ■ red) | *Contained interruption*: the flow stops at a wall | ■ + reason; the spine segment after it hollow | A-01 cross-fade; the halo goes out (light = work, E-48) | none | instant | reason first (Flighty, E-63) |
| **Retrying** (attempt n) | *Same path, again* | ● + "attempt 2 of 3" | the attempt number changes (A-01) | as executing | instant | the attempt count |
| **Verifying / reviewing** (`verifying`/`reviewing` ●) | *Checking before claiming* | ● on the spine's Verify or Review station | the spine advances (A-01) | as executing | instant | "Verifying: running tests" |
| **Completed** (`done` ✓ green) | *Resolution*: the light comes home and rests | ✓; the spine full; the halo released | short: A-01 only. Significant (§7): resolution signature, ≤ 900 ms | none | instant | the result first ("Done · 214 tests passing · 12 min") |
| **Failed** (`failed` ✕ red) | *Controlled disruption → stable error*: the light goes out | ✕ + reason + next actions | A-01 cross-fade; the halo goes out instantly; **no shake, no red flash** (WCAG 2.3.1 names red as the most dangerous flash, E-51) | none | instant | reason first, then "Retry · Open" |
| **Paused** (`paused` ‖ grey) | *Held* | ‖; light drops to mark | A-01 | none | instant | "Paused by you" |
| **Offline / reconnecting** | *Memory, not observation* | no halos (nothing is observed live) + "as of 14:02" | on reconnect, halos return in one 240 ms step and the strip says what changed | none | instant | banner, announced |

**State precedence, for every aggregate** (strip, mark, tray, the phone badge, a cluster's summary
glyph). Adapted from the taskbar's ERROR > PAUSED > NORMAL > INDETERMINATE (E-45) [I]:

> needs you > failed / blocked > unresponsive > active / verifying / reviewing > planning >
> approved > paused > done > neutral

V1 already orders Now with attention first. Whether V1's mark and cluster aggregation follow
exactly this order needs a check against ADR-0024's presentation classes before it is written as
a rule.

**What this deliberately does not do.** It gives no state a loop: not thinking, not waiting, not
asking. The user approved the rejection of `sin(T)` breathing on 2026-09-29 (rulebook §2.6), and
this research only strengthens it: a breathing "waiting" loop beside content would fall under
WCAG 2.2.2, cost CPU while idle (13 % for a blinking cursor, E-51), and habituate after the
second exposure (E-50).

---

## 6. Motion language: grammar, intensity, fatigue, choreography

The main doc's §7.4 (duration classes, the signature table, "motion is proportional to evidence")
stays. This section adds the grammar, the intensity hierarchy, the fatigue rules and the
choreography.

### 6.1 The spatial grammar

Motion follows meaning along three fixed axes, so the same direction always means the same thing:

- **Depth = focus.** Forward means "you are working on this" and back means context. Opening
  comes forward and closing goes back.
- **Horizontal = lifecycle time.** The spine runs left to right, past to future. Progress moves
  right, and nothing ever moves left except "back" in navigation.
- **Vertical = priority.** New attention arrives at the top of its group and nothing slides in
  from below.

| Category | Metaphor | Duration | Easing | Direction | Level (§6.2) | Reduced motion |
|---|---|---|---|---|---|---|
| **Arrival** (Core created an object) | It was always going to be there | 0 (rows appear at once, §46.2) + the thread rule marks it | — | none | normal | same |
| **Departure** | It is finished with you | 0 for rows; 160 ms opacity for transient layers | effects (no overshoot) | none, or back in depth | normal | instant |
| **Expansion** (row → detail, panel → page) | The same object, closer | **`morph` 320 ms (new)** | standard spatial, ≤ 4 % overshoot (main doc §7.4; M3 standard `(.27,1.06,.18,1)`, E-42) | forward | focus | cross-fade 160 |
| **Collapse** | The same object, put back | 280 ms (`layer`) | same | back to its origin | focus | instant |
| **Transformation** (item → turn, node → mission) | It became the next thing | `morph` 320 | same; content cross-fades and is pinned to the top edge (E-42) | from the object to its new place | focus | cross-fade 160 |
| **Progress** | Moving along a known path | 160 per spine station | effects | right | normal | instant |
| **Attention** | Something needs you | 240 once (A-08) | effects | none (in place) | attention | static band |
| **Success** | The light comes home | 160 (A-01); significant ≤ 900 (§7) | effects; `travel` linear | right then rest | normal / hero | instant |
| **Failure** | The light goes out | 160 (A-01) | effects | none — **no shake** | focus | instant |
| **Waiting** | Armed, still | 0 | — | — | ambient | same |
| **Reconnection** | Observation resumes | 240 one step | effects | none | normal | instant |
| **Navigation (peer sections)** | Same place, other view | 120 quick fade (Fluent top-level "quick fade", E-41) | linear opacity | none | normal | instant |
| **Navigation (drill in/out)** | Into the object | `morph` 320 | standard spatial | forward / back | focus | cross-fade 160 |

**Easing pairs (new tokens):**

- `--ease-effects`: V1's `cubic-bezier(.22,.8,.18,1)`, unchanged.
- `--ease-spatial`: a `linear()` approximation of a standard spring, ≤ 4 % overshoot, for
  `morph` only.

Nothing else overshoots.

### 6.2 The intensity hierarchy

The application should not give every screen or event the same intensity. Five levels, each with
its own tools and its own budget [I] (Carbon's productive/expressive split, E-42, extended):

| Level | When | Allowed | Budget |
|---|---|---|---|
| **Ambient** | Background system state | Static light only: the strip's state line (§8), the mark, halos | **0 frames at idle**; a change cross-fades in one step |
| **Normal** | Everyday interaction | `instant` / `quick` / `standard`; A-01 state changes; row pulses | Each ≤ 240 ms |
| **Focus** | The mission, conversation or graph you are in | `morph`, the focus plane, travelling markers, camera settle | ≤ 320 ms per transition (travel 600 per marker) |
| **Attention** | Something requires you | One arrival; a band; an announcement; a phone push (P20) | Once per item; then changes form (F-4), never repeats |
| **Hero** | A rare, significant transition (§7) | The resolution signature, the handover reveal, the plan-arming thread | **≤ 900 ms**, skippable by any input, gated by significance and frequency (F-1, F-2) |

A screen has a ceiling as well as an event:

- Resources and Appearance never rise above **normal**.
- Now, Conversation and Mission reach **focus** and, rarely, **hero**.
- Attention reaches **attention**.
- Relations reaches **focus**, plus one productive multi-hop travel (§11).

### 6.3 Repetition and fatigue rules (proposed)

Grounded in:

- NN/g: "nice the first time, … annoying" (E-50);
- the visual-cortex drop after the second exposure, and the resistance of polymorphic warnings
  (E-50);
- 85–99 % non-actionable clinical alarms (E-50);
- severity-scaled persistence in the macOS dock and `FlashWindowEx` (E-45).

No controlled study of products that decay their own animation was found (E-50, gap). These rules
are inference from those sources.

- **F-1 Frequency demotes.** An event class that fires more than N times in M minutes plays its
  next lower signature. Example: more than 3 completions in 10 minutes → A-01 only, plus one
  summary line. N and M are tuned in prototype PR-6 (§18.3).
- **F-2 Significance promotes.** Only events that pass a written significance test may reach
  hero:
  - a mission that ran ≥ 10 min;
  - one that carried an approval;
  - the first open after ≥ 4 h away.

  Significance comes from Core facts, never from novelty or randomness.
- **F-3 First of the session, not first of all time.** The handover moment (§7) plays once per
  absence. No "first-run" spectacle that is never seen again. No randomised variants. The polymorphic
  finding (E-50) is about warnings that must keep being noticed, and F-4 applies it there. A
  satisfying moment works because it is rare, not because it varies — that is the Not Boring
  precedent (E-65).
- **F-4 Unresolved attention changes form, never repeats.** An unanswered approval moves up its
  group, then reaches the phone (P20), then is named in the state sentence. It never pulses again
  (E-50 polymorphic; alarm fatigue).
- **F-5 Every motion is interruptible.** Any input renders the end state at once (V1's
  `renderAt(t)` already makes this exact), as Apple's "let people cancel motion" requires (E-39).
- **F-6 The edge of vision gets only the least distracting motion.** In the periphery (rows not
  in focus, the strip, the mark), motion is limited to the pulse and blink class. Travelling
  motion is reserved for where the user is looking (E-49).
- **F-7 The user sets the ceiling.** V1's motion preference (`system | reduced`, ADR-0044)
  gains a third value, **`quiet`**: everything stays except hero, so the ceiling becomes focus.
  `reduced` keeps its V1 meaning. WCAG 2.2.2 is met by construction, because nothing runs longer
  than 5 s.

### 6.4 Interface choreography: one continuous environment

**Can Archeus feel like one continuous environment rather than a collection of pages?** Yes — by
**object constancy**, not by turning it into a spatial canvas. The rule [I]: when the user moves
from an object to its detail, the object itself carries them there.

| Transition | Choreography | Shared elements | Mechanism |
|---|---|---|---|
| **List row → mission** | The row expands into the mission view; its glyph becomes the mission header's state figure; its spine becomes the full spine | glyph, title, spine | View Transition, `view-transition-name` = object id |
| **Inspector → full mission** | The inspector panel grows to fill the content area | header, spine | View Transition |
| **Attention item → conversation** | The approval row becomes the decision card in the mission's conversation, in place | ◆ glyph, title | View Transition |
| **Graph node → mission** | The node's state figure lifts out of the canvas and becomes the header figure | figure, label | A DOM proxy placed over the node's rect, then a View Transition (the canvas node itself is not a DOM element) |
| **Execution state → result** | The running row's halo releases and the liveness line is replaced by the result line, in place; no navigation | the row | V1 A-01 plus the halo fade |
| **Peer section → peer section** | Quick fade; nothing travels | — | CSS / View Transition root fade |
| **Command bar → object** | The chosen result becomes the object's header | title | View Transition |

**Constraints:**

- Snapshots animate on transform and opacity only.
- `prefers-reduced-motion` → `::view-transition-group(*){animation:none}` plus a 160 ms
  cross-fade, or instant.
- Every transition is interruptible (F-5).
- Same-document View Transitions are Baseline and present in Chromium 140 (E-56). React 19.3
  ships a `ViewTransition` component (E-53), so the client adds 0 KB.
- **Owed measurement:** View Transitions inside the Qt shell on an integrated GPU — frame p95 and
  tearing (prototype PR-2, §18.3).

---

## 7. Hero moment map

The brief's critical test is the 100th use. Each candidate is judged on it, with the intensity
level it should reach.

| Candidate | Is drama useful? | Feel | What it communicates | Duration | Skippable | Reduced motion | 100th use | **Verdict** |
|---|---|---|---|---|---|---|---|---|
| **Opening Archeus** | Only after an absence | Reassurance, "here is where things stand" (handover) | What changed while you were away; what needs you | ≤ 900 ms: the state sentence, then the thread rules of changed rows appear in one stagger | any input | all at once | Once per absence (≥ 4 h); otherwise instant — fine at the 100th | **Hero, gated (F-2, F-3)** |
| **Entering a mission** | No — frequent | Continuity | Same object, closer | `morph` 320 | yes | cross-fade | Frequent, so it stays focus-level | **Focus** |
| **A plan becoming active (approval)** | **Yes — the trust moment** | Deliberate, committed | Authority handed over, and where execution will start | ≤ 900: the decision commits, the thread runs from the decision to the Execute station, the station arms (◇) | any input | the station arms at once | Approvals are frequent: significant ones (≥ 3 tasks, first in the mission) play hero; the rest play A-01 (F-1) | **Hero, gated** |
| **Mission begins execution** | No — often unattended | Alive | Work has started | the halo appears (static) | — | same | Fine | **Normal** |
| **Mission completes** | Yes, when significant and seen | Satisfaction, not celebration | Done, *after* verification — never before (Lee & See calibration, E-52) | ≤ 900: the light runs back along the spine to Done, the halo releases, the result line appears | any input | instant | Significance-gated; off-screen completions get V1's toast and the handover summary instead | **Hero, gated** |
| **Mission fails** | No | Clarity, recoverability | Why, and what you can do | 160 (A-01); the light goes out | — | instant | Fine at the 100th | **Focus — never hero** |
| **Important approval request** | No (alarm fatigue) | Calm urgency | What needs you, and why | 240 once | — | band | Changes form if unanswered (F-4) | **Attention** |
| **Opening Relations** | A little, on the first open per session | Discovery | Your work's shape around the focus | ≤ 600: the ego graph's edges draw outward hop by hop from the focus | any input | drawn at once | First open per session only | **Focus** |
| **Navigating a dependency path** | **Yes — it is the answer** | Understanding | How A caused C | travel per hop, ≤ 1.2 s in total; the path stays lit | any input | the path appears lit | User-initiated, so never fatiguing | **Focus (productive)** |
| **Reconnecting after offline** | No | Relief, control | Observation resumed; what changed | 240 one step + the strip sentence | — | instant | Fine | **Normal** |
| **Completing a major workflow** (a goal, a week) | Yes, as a *reflective* artefact, not an animation | Accomplishment | What the week's work was | On demand: a still "constellation of the week" (Flighty Passport, E-63; repo-vis fingerprint, E-64) | n/a | n/a | Visited rarely by choice | **Emotional — V2 Later** |

**Four hero moments in the whole product** — handover, plan arming, significant completion, and
the causality path — each gated and each one meaning something. That is the "small number of
spectacular experiences" the brief asks about, and it is the pattern of every reference that
survived daily use (E-63, E-65, E-66).

---

## 8. Ambient visualization

**The rule (from the brief, and Mankoff's "peripherality" heuristic, E-48):** ambient
visualization must communicate something or establish identity. It must stay unobtrusive unless
it requires attention. And if it is removed, the user must lose something nameable.

| Concept | Communicates? | Verdict | Why |
|---|---|---|---|
| Slowly evolving gradients | No | **Reject** | The legacy stage (E-38); the V1 surface-gradient ban; fails the removal test |
| Light fields / particle fields | No | **Reject** | E-38 "overstimulating"; WCAG 2.2.2; CPU while idle (E-51) |
| Flowing lines (continuous) | No | **Reject as ambient** | The same lines as **events** are the thread and the markers |
| Graph energy | Yes, per batch | **Keep as V1 events** (pulse, marker) | Already proportional to real signal (Live Wire, E-48) |
| Execution trails | Yes: where this execution has been | **Adapt as static**: while an execution is live, the edges it has traversed keep a faint static `active` stroke; cleared when it ends | 0 frames; memory of motion without motion |
| State-driven illumination | Yes | **Adopt one channel: the state line.** The operations strip's 1 px top rule takes the colour of the highest-precedence state (§5): amber when something needs you, blue when work is live, nothing at idle. It changes only on a state change, in one 160 ms cross-fade | The Ambient Orb and taskbar precedent (E-45, E-48): one peripheral channel and one mapping. 0 frames at idle |
| Environmental motion | No | **Reject** | — |
| OS-level presence (tray and taskbar overlay in the state colour) | Yes, outside the app | **V2 Later, investigate** | Qt 6 has no WinExtras; this needs a native call — feasibility unverified |

**Cost of the adopted ambient elements** (the state line and static trails):

- CPU, GPU and battery: 0 frames at idle; a cross-fade per change.
- Mobile: the state line also tops the phone's Now.
- Accessibility: never the only carrier; the strip sentence holds the same information.
- Reduced motion: instant change.
- High contrast and forced colours: a solid 2 px rule in the system colour.
- Offline: no colour, plus "as of".
- Low-end hardware: nothing to drop.

---

## 9. Typography and colour direction

### 9.1 Typography: a stronger identity, still with no web fonts

**[A/R]** The fonts V1 already names are variable fonts on Windows 11:

- Segoe UI Variable: wght 300–700, optical size 5–36;
- Cascadia Mono: wght 200–700.

That is a typographic system at 0 KB that V1 uses at fixed weights only (E-57).

- **Optical size as identity.** The `display` role uses Segoe UI Variable's Display optical size
  (opsz 28–36). It changes the letterforms, not only the size — tighter spacing and finer detail —
  and makes the state sentence read as a headline set in type rather than enlarged body text.
  Proposal: `display` 32/38 desktop (from 28/34), opsz auto, wght 560.
  **Owed:** check that `font-optical-sizing` reaches the local font inside Qt (E-57 gap, PR-4).
- **Precise weights.** Variable weights allow 450 / 560 / 640 instead of 400 / 600 — the
  restrained precision that reads as premium. One rule: row titles 560, body 400, meta 400
  tertiary ink.
- **Typography carries state at rest (0 frames):**
  - a running mission's title is primary ink at 560;
  - a done mission's title relaxes to secondary ink at 450 — resolved work quietens;
  - a needs-you title keeps 560 plus the band.

  Weight and ink are never the only carrier; the glyph and the word stay.
- **Numerals are an instrument readout.** Cascadia Mono tabular numerals in the meta column (main
  doc §7.1) and in durations and counts. Kinetic numerals only where the number changed because
  of an event: one vertical step of ≤ 160 ms on the changed digit column (transform). No
  odometer spins and no counting up.
- **The streamed message is the kinetic typography.** Archeus's text arriving is the real signal.
  No typewriter, scramble or shimmer effects (E-44, E-62).
- **Typography as navigation.** Each clause of the state sentence ("3 missions running · 1 thing
  needs you") is a link to what it names. Whether V1's sentence already links its clauses needs a
  check before this is proposed as new.
- **Phone:** SF Pro and Roboto on the same roles. SF Pro's optical size is automatic (E-57).

**Rejected:** a display web font (the offline rule); Bahnschrift as a second display family (two
families are the limit; the legacy used it, and it reads as the old app); kinetic display type.

### 9.2 Colour as a dynamic state system

- **No new hues.** The six fixed state colours stay. Colour gets more expressive through **light
  levels** (none, mark, halo, event; §5), not through more colours.
- **Controlled transitions.** A state change cross-fades in 160 ms (A-01). The state line and
  halos change in one step. No colour animates continuously, and there is no gradient on any
  surface.
- **The one gradient** remains the thread's travelling highlight (DS §6). This addendum gives it
  a specified light quality (§16.3).
- **OKLCH as the authoring space.** Surfaces, ink levels and light levels are defined as OKLCH
  ladders and generated into static tokens at build time (`oklch()` is Baseline high, E-56). Even
  perceptual steps are part of what makes the dark UI feel crafted. Linear generates whole themes
  from three variables the same way (E-61).
- **High contrast and forced colours.** Halos become solid 1 px rings; the state line becomes a
  2 px system colour; the thread becomes 2 px `focus` ink (V1); the scrim and edge light are
  dropped.

**Mapping of the brief's states to colour (V1 colours):**

| State | Colour |
|---|---|
| Thinking / planning | violet |
| Attention / approval needed | amber |
| Approved | ink (◇) |
| Executing | blue |
| Success | green, after verification |
| Warning | no separate hue: amber if the user must act, text otherwise |
| Failure | red, only if a person must resolve it |
| Connection | ink |
| Offline | grey, plus "as of" |
| Paused | grey |

---

## 10. Hero surfaces and the V2 Wow Map

### 10.1 Which surfaces deserve more visual attention

| Surface | Character | Ceiling (§6.2) | Why |
|---|---|---|---|
| **Now** | Calm, ambient, typographic | Hero, for the handover only | The first thing seen; its beauty is the state sentence and stillness |
| **Mission execution** | Data-dense, alive | Focus, plus hero at completion | Where the light runs: spine, halo, liveness |
| **Relations** | Spatial, interactive | Focus, plus the productive causality travel | The signature place (§11) |
| **Attention** | Calm, dense, decisive | Attention | Obligations, not spectacle (alarm fatigue) |
| **System status (strip, mark)** | Ambient | Ambient | One peripheral channel |
| Conversation | Calm, typographic | Focus | Cards plus the thread |
| Resources, Appearance | Quiet | Normal | Forms |

### 10.2 The V2 Wow Map

| Surface | Current V1 feel | Desired V2 feeling | Visual opportunity | Motion opportunity | Spatial opportunity | Risk |
|---|---|---|---|---|---|---|
| **App shell** | Correct, flat, a little austere | Crafted, settled, native to Windows | Tonal elevation ladder, edge light, concentric radii, a dimmed sidebar ("felt not seen", E-61); the state line on the strip | Quick fade between sections; `morph` on drill-in | The focus plane for modal layers | Low: tokens only. Over-tuning chrome until it reads as a theme |
| **Now** | Quiet, partly crowded by cards | "Here is where things stand" — calm authority | Display optical size for the state sentence; the meta column; compact Decide rows | The handover reveal once per absence; thread rules for what changed | none (the flow strip, main doc §8.3) | Medium: handover gating must be right, or it becomes a daily nuisance |
| **Conversation** | Live cards, the T1 thread | A conversation with consequences | Cards with the spine; typographic hierarchy in streamed text | The thread with full light quality (§16.3); card → mission `morph` | none | Low |
| **Mission** | A state word and a status line | An object with a life you can read at a glance | The spine as the central figure; weight and ink carry state | Plan arming and resolution (hero, gated); stations advancing | Focus plane when an approval opens | Medium: needs P21 data for the action figures |
| **Attention** | Core order, full cards | Decisive, never alarming | Grouped by obligation; the static band; ◆ in amber only | Arrival once, then changes form (F-4) | none | Low |
| **Relations** | Canvas 2D constellation, a list mirror | "This is the shape of my work" — discovery | Semantic zoom tiers; state figures; static execution trails; "since you looked" ink | First-open hop reveal; the causality path's light; camera settle | 2D depth tiers (alpha by hop) — no 2.5D, no 3D | Medium: the 60 fps owed on integrated GPUs; risk of becoming Obsidian's hairball (E-30) |
| **Execution** | Halo, pulse, marker | Alive but controlled | Liveness text; attempt counts; the result line in place | One pulse per batch at the edge of vision; markers in focus | Static trails in Relations | Low |
| **Resources** | Forms | Trustworthy, quiet | Health roll-up (main doc P-8); meta column | none beyond normal | none | Low — keep it plain |
| **Appearance** | Theme, contrast, motion | In control of intensity | A live preview of the motion level | The new `quiet` level (F-7) | none | Low |
| **Offline** | Read-only snapshot | Honest memory | No halos; "as of" in meta | One step on reconnect | none | Low |
| **TUI** | Parity, no motion | The same instrument in characters | `│` thread rule; spine as `◌─●─◇─○`; the state sentence | none (TUI has no motion, by rule) | none | Low |

---

## 11. Spatial Relations as the signature place

**The question.** Could Relations become something users immediately associate with Archeus? The
evidence has two sides:

- **Recognition is real.** Obsidian's graph is the most recognised view in its category (E-30),
  and Wattenberger's repo fingerprint is learned by repetition and loved for being *yours*
  (E-64).
- **Utility is fragile.** Obsidian users "never found it helpful" (E-30); research shows no
  comprehension gain from 3D (E-8); GitHub had to add proof of life (E-60).

**So the signature must be beauty that is also an answer.** The proposal [I], in order of value:

1. **A stable fingerprint.** Layout once, positions persistent (V1, R4). Your constellation keeps
   its shape across days, so it becomes recognisable — a property no 3D camera or force
   animation has.
2. **The causality path as light.** "Why did this change?" lights the path hop by hop from origin
   to effect (after P21 Q-B1). It is the one multi-hop travel in the product (§7), and the most
   meaningful use of light Archeus can make.
3. **Mission origin.** The thread from the conversation turn that started a mission to the
   mission node — where work came from.
4. **Focus neighbourhoods.** An ego graph at depth 1 by default (main doc P-6). The rest recedes
   by V1's alpha tiers, plus thinner strokes for the far tiers: depth without blur or 3D.
5. **Semantic zoom tiers** (main doc §8.1). When a node crosses a tier threshold it cross-fades
   between representations (dot → figure → figure + label → figure + label + spine). Discrete
   swaps, not continuous morphing.
6. **Temporal: then vs now, not replay.** "Since you looked" marks new nodes and edges in thread
   ink until acknowledged (static). A two-time comparison (Open MCT's "then vs now", E-33) instead
   of animation; V1's "no replay" stands.
7. **Static execution trails** while an execution is live (§8).
8. **Proof of life everywhere.** Hovering any light — halo, marker, trail — names the execution
   and the frame that caused it, and a click opens it (GitHub's rule, E-60). A light that cannot
   be asked "why" is decoration.

**Rendering verdict:**

- **2D Canvas, as V1.**
- **Animated edges only per real event.**
- **No 2.5D tilt or parallax** — vestibular risk, and the depth tiers already carry depth.
- **No shaders and no three.js** — the legacy record, and the shell offers WebGL 2 only (E-38,
  E-55).
- **WebGL 2D (sigma, 26 KB BP) only on the measured trigger** in main doc §5.2.
- **GPU layout libraries (cosmos.gl, 157 KB) are not needed:** layout runs once and the cap is
  500.

**A beautiful 2D graph is the superior choice here**, and the research and the legacy record both
say so.

---

## 12. Emotional design

Mapped to Norman's three levels and to Walter's hierarchy, where delight counts only once
function, reliability and usability hold (E-52). One more constraint applies: Lee & See's
**calibration** — the interface must never show more confidence than Core has.

| Workflow | Intended feeling | Norman level | Design means | Never |
|---|---|---|---|---|
| **Approval** | Deliberate, trustworthy | Behavioural / reflective | The full plan in view, at SAT levels 1–3: what, why, projected outcome (E-52); an explicit verb ("Approve push"); the consequence drawn — the thread to where execution starts | Hold-to-confirm theatre, countdowns, approvals that time out into action |
| **Execution** | Alive but controlled | Visceral / behavioural | Halo + a pulse per batch + liveness text; the e-stop always reachable; markers only where you look | Spinners, shimmer, progress invented without data |
| **Completion** | Satisfying | Visceral | The resolution signature (significant only); the result first ("214 tests passing · 12 min"); ink relaxes to secondary | Confetti, sound, celebrating before verification |
| **Failure** | Clear, recoverable | Behavioural | The light goes out; the reason first (Flighty, E-63); next actions offered; red only if a person must resolve it | Shake, red flash, alarming copy, a toast for a failure the user is looking at |
| **Exploration** | Discoverable | Reflective | Proof of life on every light; the causality path; the first-open hop reveal | A hairball, an intro animation every time |
| **Return after absence** | Anticipation met, calm | Reflective | The handover reveal, once | A daily-greeting persona |
| **Long-term** | Accomplishment, ownership | Reflective | A stable constellation; the week's retrospective on demand | Streaks, scores, badges (gamification) |

**Gamification: rejected.** It improves no Archeus workflow, and it pulls trust away from
calibration, toward reward.

---

## 13. Wow or gimmick: classification of every technique

The brief's five classes:

- **Pr** — productive beauty: clearer and more memorable.
- **Em** — emotional beauty: important moments feel meaningful.
- **Am** — ambient beauty: atmosphere without interference.
- **De** — decorative beauty: purely aesthetic, used sparingly.
- **Gi** — gimmick: impressive in a demo, annoying or confusing in repeated use.

| Technique | Class | Verdict |
|---|---|---|
| Thread light: head, tail, landing ring (§16.3) | Pr / Em | **Core** |
| Lifecycle spine stations filling | Pr | **Core** |
| Static halo; pulse per batch; travelling marker in focus | Pr | **Keep (V1)** |
| Causality path light | Pr | **Later (after P21)** |
| Container transforms / object constancy (View Transitions) | Pr | **Core (U2)** |
| Focus plane recession | Pr | **Core (U2)** |
| Tonal elevation, edge light, concentric radii, 1 px strokes | Pr / Am | **Core (U1)** |
| Optical-size display type, precise weights, ink levels | Pr / Am | **Core (U1)** |
| Weight and ink as state at rest | Pr | **Core (U1)** |
| State line on the strip | Am | **Core (U3)** |
| Static execution trails | Pr / Am | **Later (U5)** |
| Plan-arming thread (hero) | Em / Pr | **Core (U3), gated** |
| Resolution signature (hero) | Em | **Core (U3), gated** |
| Handover reveal (hero) | Em | **Polish (U6), gated** |
| Relations first-open hop reveal | Em / Pr | **Later (U5)** |
| Kinetic numerals (one step on change) | Pr | **Later**, optional |
| Week constellation retrospective | Em | **Later** |
| Hover lift (−1 px + pre-rendered shadow cross-fade) on cards | De | **Allowed sparingly**: conversation cards only, never rows |
| Pointer-following light on cards | De → Gi | **Reject** (a paint-property loop on every move; means nothing) |
| Parallax, tilt, perspective cards | Gi | **Reject** |
| Glass, blur, frost, refraction | Gi (here) | **Reject** |
| Bloom, glow fields, light leaks | Gi | **Reject** |
| Particle fields, generative backgrounds | Gi | **Reject** |
| Breathing, shimmer, orbs, spinner verbs | Gi | **Reject** |
| Scroll-driven storytelling, scrubbed sequences | Gi (in an app) | **Reject** in the app; allowed on the site |
| Scrambled or kinetic display type | Gi | **Reject** |
| Confetti, celebratory bursts, sound | Gi | **Reject** |
| 3D globe or scene, shader heroes | De | **Site only** |
| Cursor fluid, audio-reactive visuals | Gi | **Reject** |

---

## 14. Anti-patterns and gimmicks to reject

Each is rejected with its evidence. Together they are a review checklist for every V2 visual
proposal.

1. **Ambient wallpaper** — motion or light behind the content that reports nothing (E-38: the
   stage, the canvases; Mankoff's peripherality, E-48).
2. **Canned activity** — shimmer, orbs, breathing, random verbs: "you look at the spinner
   expecting to understand the current state, but get a meaningless word" (E-44).
3. **Glass and blur** — the readback that tears the Qt surface; legibility backlash; Microsoft's
   own GPU warning (rulebook §24, E-40, E-41).
4. **Glow as decoration** — "overuse of glowing elements" (rulebook §27); bloom judged
   "overstimulating" (E-38).
5. **3D for its own sake** — no comprehension gain (E-8); a 249.9 ms p95 collapse (E-38); WebGL 2
   only in the shell (E-55).
6. **Marketing techniques inside the app** — scroll-driven cameras, cinematic transitions,
   kinetic type (E-62: single-visit spectacle).
7. **Celebration and gamification** — confetti that "steals focus" (E-65); reward pulling trust
   away from calibration (E-52).
8. **Motion on frequent interactions** — "nice the first time" (E-50); HIG (E-39).
9. **Travelling motion in the periphery** — "by far the most distracting" (E-49).
10. **Repeating the same alert** — 85–99 % non-actionable alarms; habituation after the second
    exposure (E-50).
11. **Any loop over 5 s beside content without a stop control** — WCAG 2.2.2 (E-51).
12. **Light without proof** — anything that glows must answer "why" on hover (E-60).
13. **Success before verification** — miscalibrated trust (E-52); resolution plays at Done, not
    at "execution ended".
14. **A display mode that changes the look** — the zen lesson (E-38).
15. **Per-theme spectacle** — skins and worlds that "could commit to nothing" (E-38).
16. **Novelty tax** — visual features users must learn for little reward (Arc, E-65).
17. **Red flashes, shakes** — WCAG 2.3.1 (red is the most dangerous flash); alarm semantics for
    recoverable states.
18. **Animating paint properties** — `box-shadow`, `filter`, gradients, colours on large areas
    (E-58; the Qt rule).
19. **WASM animation runtimes and CDN-fetched engines** — Rive and dotLottie fetch 0.37–0.93 MB
    of WASM from a CDN by default (E-53); this conflicts with the offline rule.
20. **Pointer-reactive lighting** — repaints on every move, communicates nothing.

---

## 15. Technology comparison for visual effects

Judged on what the visual direction above actually needs:

- finite transforms and opacity steps;
- container transforms between DOM states;
- line drawing (the thread, the spine);
- a Canvas 2D graph;
- static tokens.

The criteria are expressive capability, performance, accessibility, bundle size, maintainability,
mobile and interaction quality. Popularity is not one of them.

| Technology | Expressive capability for this direction | Performance | Reduced motion / a11y | Bundle | Maintainability | Mobile | **Verdict** |
|---|---|---|---|---|---|---|---|
| **CSS transitions and keyframes** | Everything in §6.1 except container transforms | Compositor (transform/opacity) | `prefers-reduced-motion` | 0 | Registry-gated (V1) | ✓ | **Use** (as V1) |
| **WAAPI** | Programmatic one-shots, `renderAt(t)` | Compositor | Manual (V1 handles it) | 0 | ✓ | ✓ | **Use** (as V1) |
| **View Transitions (same-document) + React 19.3 `ViewTransition`** | Container transforms, object constancy (§6.4) | Snapshots on the compositor; Qt **unmeasured** | `animation:none` under reduced motion | 0 | Names per object id | ✓ (Safari 18) | **Adopt in V2-U2**, after PR-2 |
| **CSS `linear()` springs** | Standard spatial spring for `morph` | — | — | 0 | Tokens | ✓ | **Adopt** (one token) |
| **SVG** (stroke-dash draw) | The thread line, spine stations, the landing ring | Draw-on via transform/opacity masks | ✓ | 0 | ✓ | ✓ | **Use** |
| **Canvas 2D** | The constellation, markers, trails | V1 one parking loop | Mirror list | 0 | V1 | List below 600 px | **Keep** |
| **`@property`, `oklch()`, `color-mix()`** | Token authoring; registered properties for one-step colour cross-fades | Paint, so never animated on large areas | — | 0 | Build-time | ✓ | **Use for authoring**; not for continuous animation |
| **Variable fonts (system)** | Optical size, precise weights | — | — | 0 | ✓ | SF Pro ✓ | **Adopt** (PR-4) |
| **WebGL 2 raw / sigma** | Very large graphs | GPU | Mirror | sigma 26 KB BP | Medium | — | **Escape hatch only**, on the measured trigger |
| **Custom shaders** | Light fields, bloom | GPU, the Qt risk | Poor | — | Low | Battery | **Reject** |
| **three.js** | 3D scenes | 133 KB+; legacy collapse | Poor | 133 KB | Low | Battery | **Reject in the app**; the site keeps it |
| **WebGPU** | Compute, the future | — | — | — | — | — | **Reject**: compiled out of Qt 6.11 (E-55); not Baseline |
| **Anime.js 4.5** | Timelines | Own ticker | None built in | 13–44 KB | Second clock | ✓ | **Reject** (main doc §5.1) |
| **GSAP 3.15** | Best-in-class timelines, Flip, SplitText; now free | Own rAF ticker, main-thread writes | Only through `matchMedia` | 28.3 KB (+9.7 Flip) | A second clock beside the parking loop and `renderAt(t)` | ✓ | **Reject**: it solves timeline choreography Archeus deliberately does not have |
| **Motion 14** | Layout animation, springs, `AnimateView` | WAAPI hybrid | Built in | 3.4 KB mini → 41.3 KB full | Released 2026-10-02 | ✓ | **Reject now**. Revisit only if View Transitions fail PR-2 *and* layout animation is still wanted (then `LazyMotion`, 7.4 KB) |
| **Motion One** | — | — | — | — | Merged into Motion | — | n/a |
| **Lottie (lottie-web)** | Designer-authored canned animations | SVG/canvas, main thread | None built in | 46–76 KB | Assets outside the registry | ✓ | **Reject**: canned loops are what §5 rules out |
| **dotLottie / Rive** | Data-bound state machines (Rive) | WASM renderer | Example only | 0.37–0.93 MB WASM; **CDN fetch by default** | Medium | Heavy | **Reject**: weight, the offline rule, and canned figures |
| **Figma Motion** | Design-time motion with spring or bezier ease; exports CSS, JSON or React | n/a | n/a | 0 at runtime | — | — | **Adopt as a design tool** for the motion registry v2 specs and prototypes. Exported CSS is a draft that must be re-checked against the registry rules |
| **Libraries.dev effects** | Beam, gooey, metal, orbs | Loops | Mixed | — | — | — | **Reject** (main doc §5.4) |
| **Custom rendering (V1 `graph/loop.ts`)** | Everything canvas-side | One parking loop | ✓ | 0 | ✓ | ✓ | **Keep** |

**Conclusion [I].** The V2 visual goal needs **no new runtime dependency**. Its new platform
surface is View Transitions, `linear()`, variable-font axes and OKLCH-generated tokens — all in
Chromium 140, all 0 KB. The one capability that is genuinely new and uncertain is View
Transitions inside the Qt shell, and that is a measurement (PR-2), not a library choice.

---

## 16. Visual signature candidates and the recommendation

### 16.1 Candidates

| Candidate | Recognised in 5 s? | Communicates | Fatigue at the 100th use | Cost | Lineage | Risk |
|---|---|---|---|---|---|---|
| **A. The luminous thread** — light only where Archeus acted, travelling from what it said to what it changed, landing, and leaving a rule | **Yes** — no other product draws causality from words to objects | Archeus's agency, made visible and traceable | Self-limiting: fires only on real actions, capped at one travel at a time | SVG/CSS, 0 KB | DNA-1, DNA-4; DS §2 "nothing else gets a signature" | Low |
| **B. The living constellation** — Relations as your work's fingerprint | Yes, when it is on screen | Context, structure, causality | Low: user-initiated | Canvas (V1) | DNA-5 | Medium: hairball, 60 fps owed, only seen when opened |
| **C. State-driven light** — the interface's illumination follows system activity | Partly | System state | Medium–high if it grows beyond one channel | Low as one line; high as a field | DR §7 "one surface behind, driven by state" | **High**: the slope back to the legacy stage (E-38) |
| **D. The typographic instrument** — optical-size display type, tabular meta, precise weights | Yes, subtly — "felt after a few minutes" | Seriousness, precision | None | 0 KB | Huw Prosser, Linear | Low, but not alive on its own |
| **E. Adaptive depth and morphing surfaces** | Partly — platforms do this now (visionOS, Liquid Glass) | Focus, continuity | Low if kept to `morph` | VT, 0 KB | — | Medium: reads as "like Apple" rather than as Archeus |

### 16.2 Recommendation: **A, the luminous thread — voiced by D, staged by B**

Do not combine all five. One signature, as the V1 design system already insists ("boldness spent
in one place", DS §1.5). **The thread is the signature**:

- it is unique to an agent system;
- it is true by construction, because it fires only when Core records an action with links;
- it cannot fatigue faster than Archeus acts;
- it costs nothing;
- it already exists in all three media: the T1 line in the app, the T2 rule in lists, `│` in the
  TUI.

**D** is the voice that makes the still state beautiful. **B** is the largest stage the thread
plays on: the causality path *is* the thread drawn across the constellation. **C** survives only
as the single state line (§8), and **E** only as craft (`morph`, the focus plane) — neither is a
signature.

**The five-second picture.** Dark, still, aligned. Fine ink lines and quiet, precise type. One
point of light leaves a sentence, runs to a row, lands with a small ring, and leaves a thin rule.
Then nothing moves until Archeus acts again.

### 16.3 The thread's light quality (proposed specification)

V1 built the thread as a line drawn on and gone. To carry the signature it needs a defined light
quality — still within transform and opacity:

| Part | Specification | Mechanism | Reduced motion | High contrast |
|---|---|---|---|---|
| **Line** | 1 px at 1×, 1.5 px at ≥ 2×, `thread` ink or the user's thread tint (P22) | SVG path | appears whole | 2 px `focus` ink |
| **Head** | A short luminous head: a pre-rendered radial sprite, ≤ 6 px across, opacity ≤ 0.9, moving along the path | `transform` on the sprite; `offset-path` or a WAAPI keyframe list | none | none |
| **Tail** | The DS §6 highlight gradient behind the head, ≤ 48 px, fading | opacity mask moved by transform | none | none |
| **Travel** | `travel` 600 ms, linear (constant speed reads as transport, not as a spring) | — | instant | instant |
| **Landing** | A ring at the target scales 0.6 → 1 and fades over 240 ms (GitHub's landing, E-60) | transform + opacity | none | none |
| **Residue** | The T2 rule on the target row stays until acknowledged (V1) | static | same | 2 px |
| **Caps** | One travelling at a time; queued travels collapse into rules (V1) | — | — | — |

**Rule note.** The head and the landing ring are light, and rulebook §27 rejects "glow as
decoration". They are not decoration — each is the thread's event, at most 600 + 240 ms, on a
real action — but the wording of §27 and DS §2/§6 should say so explicitly before this is built.
That is decision **V-D1** (§18.1).

---

## 17. The smallest set of principles: the foundation for V2 visual architecture

**The question.** What is the smallest set of visual principles that could make Archeus feel
dramatically more beautiful and distinctive without making it dramatically more complicated?

**Five principles**, each with its rule and its cost. This is the proposed foundation for the V2
visual architecture: each principle becomes a section of an ADR or a design rule (§18.2), and
each rule becomes a token or a gate.

| # | Principle | The rule it becomes | Its cost |
|---|---|---|---|
| **V-1** | **Light is evidence.** | Only Core-recorded work emits light; light travels only along a recorded path; every light answers "why" on hover; no light at idle. The thread is the one signature, with the quality of §16.3. | SVG/CSS; the existing registry; the existing idle-invariant gate |
| **V-2** | **Stillness is the canvas.** | Zero frames at idle (V1). The resting interface is made beautiful by type (optical size, precise weights, three inks, tabular meta), alignment, and the tonal depth ladder. | ~12 tokens; no runtime |
| **V-3** | **Depth means focus.** | Opaque planes; elevation by lightness plus edge light plus static shadow; the focus plane is the only depth motion; no blur, glass, parallax or 3D. | Tokens + one transform |
| **V-4** | **Objects persist.** | Moving from an object to its detail is a transformation of that object (`morph` 320 ms, View Transitions); peer navigation is a quick fade. | Platform; one measurement (PR-2) |
| **V-5** | **Intensity is earned.** | Five intensity levels with ceilings per screen; four gated hero moments; fatigue rules F-1…F-7; unresolved attention changes form rather than repeating. | A significance test over Core facts; one more motion preference value |

**Maximum perceived sophistication per unit of complexity [I].**

- V-2 and V-3 change how every screen looks at rest, for the cost of tokens.
- V-4 changes how the whole product feels to move through, for the cost of a platform API.
- V-1 and V-5 make the few moments that matter unforgettable while keeping the other ten thousand
  quiet.

None of it adds a dependency, a loop, a shader or a 3D scene.

---

## 18. What this changes in the V2 research, the roadmap and the next documents

### 18.1 Decisions this addendum asked the user for — decided 2026-10-04 (§30, rulebook §46.4)

| Id | Decision | Recommendation → **decided** |
|---|---|---|
| **V-D1** | Reword rulebook §27 / DS §2, §6 so that the thread's head and landing ring are allowed light (an event, ≤ 840 ms) while "glow as decoration" stays rejected | Yes → **Yes** (rulebook §27 now says so) |
| **V-D2** | Adopt the luminous thread as the V2 visual signature (§16.2) | Yes → **Yes, the leading signature; not implemented** |
| **V-D3** | Add `quiet` to the motion preference: everything except hero (F-7) | Yes → **Yes, as a design rule** |
| **V-D4** | Adopt the four gated hero moments (§7), including the handover reveal on Now | Yes, subject to PR-6 → **Yes, prototype-gated** |
| **V-D5** | Raise `display` to 32/38 with the Display optical size (§9.1) | Yes, subject to PR-4 → **Yes, prototype-gated; no global increase before PR-4** |

### 18.2 Changes to [ARCHEUS_V2_UI_RESEARCH.md](ARCHEUS_V2_UI_RESEARCH.md) (proposed, not yet applied)

- **§7.1 Typography:** add optical size, precise weights, weight and ink as state (§9.1).
- **§7.3 Surfaces:** add the tonal ladder, edge light, scrim, concentric radii and focus plane
  (§4). "No blur, no glass, no surface gradients" stays.
- **§7.4 Motion:** add the `morph` class (320 ms) and `--ease-spatial`; the spatial grammar
  (§6.1); the intensity levels (§6.2); the fatigue rules (§6.3); choreography (§6.4).
  **Promote** View Transitions from "DEFER, V2-U6" to V2-U2, conditional on PR-2.
- **§7.6 Colour:** add the light ladder and state precedence (§5).
- **§10.3 Never:** narrow "glow" to "glow as decoration" (V-D1). Every other entry stands, and
  this research reinforces it.
- **Roadmap (§12 of the main doc):**

| Phase | Adds |
|---|---|
| U1 Foundation | Depth tokens, typography (optical size, weights, inks), intensity levels, motion classes |
| U2 Interaction | Object constancy (View Transitions), the focus plane |
| U3 Living state | The state-picture catalogue, the state line, the thread's light quality, the plan-arming and resolution moments |
| U5 Relations | The signature place (§11) |
| U6 Polish | The handover reveal, kinetic numerals, the week's retrospective |

  The ordering and the dependencies on P20, P21 and P22 are unchanged.

### 18.3 Prototypes owed, each with a kill criterion

| Id | Prototype | Pass | Kill |
|---|---|---|---|
| **PR-1** | Thread light quality (§16.3) in the Qt shell on integrated graphics | p95 frame ≤ 16.7 ms during travel; no tearing; idle invariant holds | Any tearing, or p95 > 20 ms → keep V1's thread as built |
| **PR-2** | View Transition container transform (row → mission) in Qt 6.11 | p95 ≤ 16.7 ms; no flash or tearing; reduced motion respected | Fails → keep V1 cuts plus a 160 ms cross-fade; reconsider Motion `LazyMotion` only if layout animation is still wanted |
| **PR-3** | Focus plane recession | No discomfort reported in a reduced-motion-off session; legible base under the scrim | Discomfort → scrim only, no scale |
| **PR-4** | Segoe UI Variable optical size and weights via CSS in Qt, the browser and Windows high contrast | Display opsz visibly applied; no layout shift at 200 % text | Not applied → keep 28/34 at 600 |
| **PR-5** | The state-picture catalogue at 12/16/20 px (§5), reviewed by the user | Every state identifiable without colour | — |
| **PR-6** | The four hero moments, dogfooded for two weeks with F-1/F-2 thresholds logged locally | The user still wants each one at the end of the fortnight (the 100th-use test made literal) | Any moment the user turns off → demote it to its normal signature |

### 18.4 Next documents

- **ADR — "Light is evidence"** (V-1, V-D1, V-D2): the signature, the light ladder, proof of life,
  the amended §27 wording.
- **ADR — "Intensity and fatigue"** (V-5): five levels, per-screen ceilings, F-1…F-7, the
  significance test, the `quiet` preference.
- **ADR — "Object constancy"** (V-4): View Transitions, naming by object id, `morph`, the
  fallbacks.
- **Design document — State picture catalogue:** the figures, rest pictures, entry signatures and
  precedence for every presentation class.
- **Design document — Motion registry v2:** every motion id with trigger, level, duration,
  easing, direction, cap, reduced-motion and text equivalents — authored with Figma Motion as the
  design tool (§15).
- **Design document — Depth and typography tokens:** the OKLCH ladders, inks, edge light,
  shadows, optical-size roles.
- **Design document — Hero moments:** the four moments frame by frame, the significance test, the
  dogfood protocol (PR-6).

---

## 19. Method and gaps

**Method.** Four parallel read-only research passes (E-38…E-66), plus this repository's own record
(the legacy GUI, `CLAUDE.md`, DR, the rulebook, the motion and presentation tokens, ADR-0044) and
the Windows font files read directly. No product, test, CI or dependency changes. No login,
nothing posted. One fetched summary misreported a paper and was corrected against the paper
itself (E-49).

**Gaps:**

- **No controlled study of adaptive animation intensity was found.** F-1…F-7 are inference from
  habituation research, NN/g and severity-scaled OS precedents, and PR-6 exists to test them on
  the actual user.
- **Nothing here was measured inside the Qt shell.** The View Transitions, optical-size and
  thread-light claims are owed to PR-1, PR-2 and PR-4. The V1 measurements still owed (60 fps at
  1,000 nodes on integrated graphics, a physical phone; R13 §6) remain owed.
- **Unconfirmed:**
  - whether the state precedence in §5 matches V1's aggregation exactly;
  - whether V1's state sentence already links its clauses (§9.1).
- **Not found:** primary sources for the ChatGPT orb's signal and the Claude app's animated mark.
- **No user testing.** "Breathtaking" is judged here by evidence and by this product's own
  history, not by watching the user. The dogfood fortnight (PR-6) is the first real test, and
  the user's judgement overrides this document.

---

# Part II — Benchmark against JARVIS-style interfaces (2026-10-04)

**The brief for Part II, restated.** Archeus should be an exceptionally appealing, premium,
visually distinctive AI/system interface — more compelling and memorable than the typical
JARVIS-style project — without becoming a noisy Iron-Man HUD clone. Part I's restraint is not the
conclusion. The question is what makes JARVIS interfaces feel futuristic, powerful, alive and
emotionally compelling, and how Archeus can deliver those same qualities through an original,
product-grade language.

Evidence: reference study §7 (E-67…E-77).

## 20. JARVIS / REEL VISUAL BENCHMARK

### 20.1 The repositories

Thirteen were read in source: the eight the user named plus the five highest-starred HUD projects
found by search (E-67). Every named repository exists. The seven strongest are below, one block
each; the other six are in the E-67 table.

**thisisreyy/jarvis — the most premium-looking of the set**

- **Visual language:** desaturated "hull" `#06070a`, ice `#84b6d6`, muted ok/warn/alert. Inter
  Tight and IBM Plex Mono. The CSS rejects the "outer neon halo" in favour of a single hairline,
  and a backlight that is "not a glow filter".
- **Layout:** a centred PBR arc reactor with telemetry rails at fixed left and right offsets.
- **State:** the reactor's emission colour changes per state and lerps to amber under load.
- **3D and lighting:** R3F, physically lit metal, image-based lighting, an orbit camera, and a
  WebGL fallback.
- **Voice:** the listening pulse is `Math.random()` every 100 ms — fake.
- **Telemetry:** mostly hardcoded ("1.21 GW").
- **Accessibility:** a CSS reduced-motion rule that the 3D ignores; `:focus-visible` styles.
- **Mobile:** no breakpoints.
- **What creates the wow:** material quality. Light comes *off a surface*; it does not *float*.
- **Useful:** state as a change of emission rather than a change of spin.
- **Decorative:** the reactor itself, and the telemetry.
- **Archeus borrows:** the material instinct — hairlines, light as a property of a surface — and
  colour-as-state.
- **Archeus avoids:** a random number posing as voice; numbers that describe nothing.

**hasibjaan/jarvis — the most self-critical**

- **Layout:** a small orb window by default, after the full-screen HUD was retired.
- **States:** IDLE, LISTENING, PROCESSING, SPEAKING, ERROR, SHUTDOWN.
- **Voice:** the edge "ripples with the audio level", from mic RMS and the reply's waveform.
- **Loop:** 30 fps, stopped when the window is hidden.
- **Telemetry:** real.
- **The finding that matters:** the author measured that the full-screen HUD cost ~24 ms per
  frame and "intermittently stalls audio playback". The orb costs 3.8 ms. He shrank the UI
  because spectacle was audibly breaking the product.
- **Archeus borrows:** measure visual cost against the thing that matters; motion from a real
  level.
- **Archeus avoids:** the "breathing" idle.

**eadmin2/jarvis_ai (179★) — the most product-like state model**

- **States:** a Canvas 2D reactor with **six states, including a separate `tool` state**
  (standby, listening, thinking, tool, speaking, error), each with its own speed, colour, glow
  and pulse.
- **Voice:** real mic level.
- **The agent drives the stage:** it pushes media panels on screen through `hud_display` tools.
- **Boot:** a cinematic sequence with audio.
- **Telemetry:** real CPU and GPU stats beside a random hex/coords line.
- **Cost:** a perpetual rAF with `shadowBlur` up to 40×DPR every frame.
- **Archeus borrows:** "tool" as a state distinct from "thinking" — Archeus's P21 action kinds;
  the agent deciding what the user should see — the thread already is this.
- **Archeus avoids:** the perpetual glow loop; decorative hex.

**bertrandmbanwi/Jarvis (37★) — the most engineered**

- **Visual language:** a primitive-to-semantic token split.
- **The orb:** a GLSL particle orb (2,400) driven by a **typed 15-parameter state table**; states
  *blend* into each other.
- **Voice:** a server-sent TTS amplitude envelope, so the visuals are speech-synced without a
  client FFT.
- **Loop discipline:** pauses when hidden; DPR ≤ 2.
- **Other:** a real cost dashboard.
- **Gap:** reduced motion lowers the DPR but not the motion.
- **Archeus borrows:** a typed state table as the single source for visuals — Archeus already
  has `presentation.json`; this argues for extending it, not adding a parallel one — and
  envelope-driven speech visuals for V2-A1.
- **Archeus avoids:** an orb as the centre.

**jincocodev/openclaw-jarvis-ui (38★)**

- **The orb:** 3,000 particles (1,000 on mobile), driven by **the TTS output's analyser**.
- **Fake signal:** the idle waveform is sine plus noise.
- **Loop discipline:** pauses on `visibilitychange`; a **user power-save mode caps rendering at
  15 fps**.
- **Mobile:** a toolbar, plus a PWA.
- **Archeus borrows:** a user-facing intensity control — Archeus's `quiet` (F-7) is the same
  idea, done by meaning rather than frame rate.

**shauryamalhotra957-wq/jarvis**

- **Hero:** an Earth globe with "satellite targeting" (2.5 MB of textures).
- **Accessibility:** **the only repo whose 3D actually stops under reduced motion**; 43 aria
  attributes; 12 breakpoints.
- **But:** the "reactor pulse" is synthesized sine sums; a perpetual rAF writes a CSS variable
  every frame; its design document specifies a light purple system that the code ignores.
- **Archeus borrows:** reduced motion that reaches the renderer, not just the CSS.

**Dix01/JARVIS — the largest**

- **The orb:** an SVG "reference dial", seven rings spinning `linear infinite`.
- **Motion and glow:** 16 infinite CSS animations plus ~25 `animate-*`; 58 blurs, 31 backdrop
  blurs, 62 box-shadows.
- **Voice:** real mic.
- **Telemetry:** real psutil.
- **Boot:** a fake kernel boot log.
- **Loop:** an always-on rAF only to display fps.
- **What it is:** the reference image of "everything glows, everything spins".

**kvdoe/jarvis-ui — the cautionary tale.** Its PRODUCT.md is the best brief in the set: it lists
"generic 'AI assistant' glowing orb products" as an anti-reference and requires reduced motion.
The code ships a wireframe glowing core that ignores reduced motion. **A good brief without gates
produces the cliché anyway** — the argument for Archeus's design gates.

**Security note, outside the visual scope.** PRUTU29/jarvis serves terminal-run, process-kill and
file-search endpoints behind `CORS(*)`, so any web page can read local files. Spectacle projects
often skip the boring parts. Archeus's loopback guard (CLAUDE.md, `_guard`) is part of what
"credible as a real product" means.

### 20.2 The five reels

Partly observed: caption, creator and one cover still each; **no video was watched** (E-69).
Motion is described only where a caption describes it.

| Reel | Status | Composition | Light and colour | Type | State and interaction | Compelling because | Product-grade | Inspiration only |
|---|---|---|---|---|---|---|---|---|
| **1** `DY_YCRYgEwi` (@jonathonmj, Z.E.R.O, 61k ♥) | still + caption | Full-screen radial network graph, floating label/value panels, a status-dot list, a top pill bar, staged on a wall TV | Navy-black; branches coloured by cluster, white endpoints, blue core | Small spaced monospace caps | Panels pin numbers onto the network | The system's structure *is* the picture | A central system view with panels, colour-by-cluster as identity (for Archeus: by state) | "$11,500" hooks, room staging |
| **2** `DY4o8dluXdK` (@lukebuildsai, 379k ♥) | still + caption | Classic monochrome film HUD on a wall screen; a person gesturing | Blue on black; amber room | Dense small text | "Hey Jarvis, wake up!" — voice wake | Wake word + gesture + revenue promise; reach is a comment-funnel | Almost nothing | The film HUD, decorative readouts |
| **3** `Dd9g4biMnS4` (@shipnotesai, 1.1k ♥) | still (viewed directly) + caption | One object centred in empty space; headline; three state pills; a caption below | Near-black, one pink accent | Bold sans headline, mono state pills | **LISTENING / THINKING / SPEAKING** named; speech "lands as a live caption. You can read it with the sound off" | One object, one accent, an explicit state model, speech made legible | Named states, caption-first speech, one accent, negative space | Words flying out of 12,000 particles (illegible mid-flight) |
| **4** `Dct1a3Yud5K` (@reznikov_engineering) | still + caption | A point-cloud human head in profile on black | Cyan field, warm orange glow inside | — | Unknown from a still | Data shaped as a person; a warm core in a cool field | The warm/cool contrast as a focus marker, at most | A humanoid face (implies sentience; uncanny) |
| **5** `DZcSLefuxRU` (@jonathonmj + @agentcoreai, 29k ♥) | still (viewed directly) + caption | A 3D "brain" of labelled clusters, a tool-tile grid *over* it, a LIVE badge, a module index on the right | Black; per-region colours, glowing filaments | Mono caps labels | Each region: "<n> neurons · firing 0.xx"; LIVE counter | The agent's architecture made spatial, labelled and "firing" | **Labelled clusters with real numbers; a LIVE/connected badge; a side index** — close to Archeus's own constellation | The brain metaphor; a grid that hides the graph |

**What the reels add to the repos [I]:**

- The two most compelling stills (3 and 5) are the two closest to a product: one names its states
  and makes speech readable, the other labels its structure with numbers.
- The weakest (2) is the purest film HUD.
- Three of five borrow their atmosphere from an LED-lit room. On a laptop at 2 pm, that atmosphere
  is not there.

### 20.3 Film-UI craft, from the people who made JARVIS (E-70…E-73)

The designers of the film interfaces say plainly what the hobby projects copy wrongly:

- **Every element has a purpose.** Hansen: "all the graphics had a purpose"; "the HUD was a
  character… each shot had a specific message to deliver".
- **Power is density read as pattern, in stable places.** Tony "knows where each piece of data
  lives" and looks "at the patterns". NASA warned Territory that operators spot anomalies, so the
  parameters must stay stable. **Stable placement plus anomaly-only emphasis** is what makes
  complexity feel controllable.
- **Real mission control is quiet.** "NASA's screens never flash 'DANGER'"; "the most
  mission-critical thing on screen is a spreadsheet of events" (JPL).
- **Even the film JARVIS fails as an interface.** 29+ elements, 87 % moving unprompted, 6 risking
  startle reactions: "a placebo interface". The emotional need it serves is real — "we want to be
  at the adult table" — and so is the cost.
- **These are "plot visualizations", not interfaces** (Coleran). "In real life, every design
  decision has a consequence… day in and day out."

## 21. What JARVIS gets right and what it gets wrong — the reel/everyday gap

| Quality | What JARVIS projects get right (evidence) | How they get it wrong (evidence) | The everyday version |
|---|---|---|---|
| **Presence** | One focal object as the system's body (12/13 repos, 4/5 reels) | An orb with no data behind it; perpetual spin (13/13 perpetual loops) | Presence that is *where work is*: the mark, the spine, the constellation (§26) |
| **System awareness** | Telemetry rails, LIVE badges, labelled clusters (reel 5) | 8/13 fabricate a live value; decorative hex | Every number is Core's (V-1) |
| **Visible intelligence** | Named states (reel 3); a `tool` state (eadmin2); "anticipates informational needs" (E-72) | Spin speed as the only state signal (kvdoe ×3.5) | Specific text + action figures + the plan appearing as recorded (§5) |
| **Cinematic state change** | State blending (bertrand); boot sequences (5/13) | Fake kernel logs; startle reactions (E-72) | Object constancy, the thread's travel and landing, gated hero moments (§24) |
| **Anticipation** | Wake-word moments (reel 2); listening rings | Wake-word theatre | The armed station ("starts after…"); the thread head arriving *before* the landing (§24) |
| **Spatial hierarchy** | Stereo depth used to separate (Hansen) | Translucent overlap everywhere (E-72); 31 backdrop blurs (Dix01) | Opaque focus planes (§4) |
| **Ambient activity** | The Live Wire instinct — the system visibly busy | Motion that never stops, so it reports nothing | The state line + pulses per batch; stillness at idle |
| **Voice reactivity** | Real mic or TTS level in 8/13 | `Math.random` amplitude (thisisreyy); sine "idle" waves | Real level only, captions first (§29) |
| **"The computer is alive"** | Things respond and change | Breathing loops at idle | Alive because something real happens (§28) |
| **Command-centre identity** | A strong, consistent look | Cyan + Orbitron in 11/13 and 8/13 — **identity by cliché**, so none is recognisable | One signature no one else has (the thread) |
| **Hero moments** | Boot, wake, completion bursts | Every moment is a hero moment, so none is | Four gated moments (§27) |
| **Mobile** | — | Responsive in 5 of 11 web UIs | First-class (arch §M) |
| **Accessibility** | shaurya stops its 3D | Reduced motion detected in 5/13, honoured by the renderer in 1/13 | A gated requirement (arch §P) |
| **Performance** | openclaw's power-save; bertrand pauses when hidden | 10/13 never pause; ~24 ms/frame audible (hasibjaan) | The idle invariant, frame budgets, Qt-measured (arch §Q) |

**The gap between "looks futuristic in a reel" and "feels extraordinary every day" [I].** A reel
is 15 seconds, seen once, in a dark room, with sound, by someone who will never use the thing. A
product is seen thousands of times in daylight, beside other work, often silently, by someone
who must trust it. Every JARVIS failure above is a property that is free in a reel and expensive
in a day:

- perpetual motion;
- fake numbers;
- glow;
- translucency;
- novelty boot sequences.

Every JARVIS success is a property Archeus can keep:

- presence;
- named states;
- real reactivity;
- one focal identity;
- cinematic change.

## 22. More impressive than a JARVIS HUD without being one: the differentiation hypotheses tested

The user's six hypotheses, each tested against the benchmark:

| JARVIS convention | Archeus alternative (hypothesis) | Evidence | Verdict |
|---|---|---|---|
| Artificial HUD graphics | Real system state visualised beautifully | 8/13 fabricate; the two most compelling reels are the two showing real structure and named states (E-69); Hansen: "all the graphics had a purpose" | **Holds.** Refinement: real state must still be *drawn beautifully* — reel 5's labelled clusters are compelling *and* real. Archeus's constellation with state and numbers is that image, honestly |
| Permanent glowing core | Quiet until actual work creates light | 13/13 perpetual loops; habituation after the second exposure (E-50); moticons (E-49); dark cockpit (E-34) | **Holds, and it is the strongest lever.** Refinement: "quiet" must not read as "off" — L1 ambient (static halos, the state line, the mark) keeps presence visible at zero frames (§23) |
| Decorative telemetry | Every visualization corresponds to Core state | "1.21 GW", random battery, hex streams; Lee & See calibration (E-52) | **Holds.** Refinement: real numbers are compelling only if *meaningful*. Show the few that matter (missions, needs-you, output age, cost), not CPU% |
| Constant 3D | Spatiality only where it means something | 7/13 3D; Coleran's "spinning globes" trope; no comprehension gain (E-8); the legacy collapse (E-38); hasibjaan's measured cost | **Holds.** Refinement: Archeus *is* spatial — in Relations, where position means relation |
| Everything animated | Stillness makes real events important | Salience is relative to the ground; JARVIS has no ground; Hansen's patterns need stable placement | **Holds** — this is the core of §23 |
| Neon cyberpunk | Premium technical / luminous / precise / calm | Cyan 11/13, Orbitron 8/13 = indistinguishable from each other; thisisreyy, the most premium, is the least neon (hairline, material, muted palette); reel 3 compels with one accent | **Holds.** Refinement: "calm" is the base, not the whole. **Luminous** must be literal — the thread is light, and at L3/L4 it should be unmistakably bright against the still ground |

**Answer.** Archeus looks more impressive than a JARVIS HUD by having what a HUD cannot:

- **contrast** — a still ground that real events light up;
- **truth** — every light can be asked why;
- **a signature nobody else has** — light that travels from words to consequences.

It avoids looking like a HUD by refusing the HUD's grammar — orb, cyan neon, Orbitron, rings,
hex, perpetual spin — rather than by being dimmer. Archeus's luminous moments should be *brighter*
than anything on a HUD, precisely because they are rare.

## 23. The Visual Impact Ladder

This replaces the names in §6.2 with one ladder for the whole product. The mapping is in the
architecture document §C.2.

| Level | Name | What is on screen | Frames | JARVIS equivalent |
|---|---|---|---|---|
| **L0** | **Calm** | No active work: typography, alignment, tonal surfaces, static marks | 0 | — (no JARVIS project has an L0) |
| **L1** | **Ambient** | Subtle state presence: static halos, the strip's state line, the mark at rest, residual traces | 0 | Its idle state is already L3–L4 |
| **L2** | **Active** | Real work: a pulse per output batch, a marker where you look, the orbit per batch, liveness text | Per event only | Constant |
| **L3** | **Significant** | Meaningful events and transitions: `morph`, the focus plane, attention arrival, thread travel and landing, the causality path, spine advances | Per event, ≤ 320 ms (travel 600 + 240; path ≤ 1.2 s) | Constant |
| **L4** | **Hero** | Rare, gated: handover, plan arming, resolution | ≤ 900 ms, a few times a day | **Permanent** |

**Can the contrast between stillness and activity make Archeus feel more dramatic than a
permanently animated HUD? Yes [R/I].**

- Peripheral motion is detected in about 1 s with under 2 % misses against a still field (E-49).
- Response drops sharply after the second identical exposure (E-50).
- An L4-at-all-times interface spends its whole budget on the baseline, so a real event in a
  JARVIS HUD can only be *more* of what is already happening.

In Archeus, the first point of light after an hour of stillness is an event the user cannot miss
and does not resent. The ladder is not a ceiling on drama; it is what makes drama possible.

## 24. Cinematic without clutter

Each technique must answer one question: does it make the system **easier to understand**, **more
memorable**, or **more emotionally satisfying**? If not, it is decorative or a gimmick.

| Technique | Film vocabulary | Archeus form | Understand | Memorable | Satisfying | Class |
|---|---|---|---|---|---|---|
| Staged reveal | Establishing shot | Handover (K-1): the state sentence first, then what changed, in one stagger | ✓ (order = priority) | ✓ | ✓ | Pr/Em |
| Focus change | Rack focus | The focus plane: the opened object forward, the context back | ✓ | — | ✓ | Pr |
| Object persistence / spatial continuity | Match cut | `morph`: row → mission, node → mission, item → turn | ✓ (same thing) | ✓ | ✓ | Pr |
| Lighting | Motivated light (light with a visible source) | The thread's light always has a source — the sentence or decision — and a destination | ✓ (cause → effect) | ✓ (signature) | ✓ | Pr/Em |
| Depth | Depth staging | Opaque elevation planes; alpha tiers in Relations | ✓ | — | — | Pr |
| Progressive disclosure | Reveal by need | Why on demand; semantic zoom tiers; proof of life on hover/focus | ✓ | — | ✓ | Pr |
| Typography | Title card | The state sentence in Display optical size (PR-4) | ✓ | ✓ | ✓ | Pr/Am |
| Visual anticipation | Setup → payoff | The armed station (◇, "starts after…"); the head travels *before* the landing; the plan's Execute station outlined while approval is pending | ✓ (what happens next) | ✓ | ✓ | Pr/Em |
| Sound-ready design | Sound design | Each L4 moment has a named silent slot; nothing visual depends on sound | — | (later) | (later) | Em (later) |
| Boot sequence | Opening titles | **Rejected:** a fake kernel log tells nothing (5/13 repos) | ✗ | ✓ once | ✗ by the 3rd time | Gi |
| Flying to information | Camera move | **Rejected:** "spinning 3D globes and 'flying' to information" (E-73); camera settle ≤ 240 ms only | ✗ | — | ✗ | Gi |
| Particle text / scramble | Title effects | **Rejected:** illegible mid-flight (reel 3) | ✗ | ✓ | ✗ | Gi |

**Cinematic, for Archeus, means editing rather than effects:**

- **match cuts** (`morph`);
- **motivated light** (the thread);
- **rack focus** (the focus plane);
- **an establishing shot** (handover);
- **setup and payoff** (arming → execution, the head → the landing).

Film language governs *which shot comes next*. None of it requires glow.

## 25. The luminous thread as an Archeus-wide grammar

The full conceptual specification is in the architecture document §J. This section is the
research reasoning behind it.

### 25.1 Manifestations

| Manifestation | Link (Core record) | Strongest moment |
|---|---|---|
| intent → plan | The user's turn → the plan | The first plan step appearing |
| plan → approval | The plan → the Decide row | The approval card arriving with its plan in view |
| approval → execution | The decision → the Execute station | **K-2 plan arming** (L4 when significant) |
| execution → resource | The execution → the harness/account/provider used | A short travel to the resource row, when on screen |
| resource → result | The execution → the result line | The landing on the result |
| result → review | The result → the Review station | Review arriving in Attention |
| review → done | The spine → Done | **K-3 resolution** |
| cause → effect | The recorded causal path (P21 Q-B1) | **K-4** |

### 25.2 The visual vocabulary

| Element | Specification |
|---|---|
| Light travel | Head + tail, 600 ms linear |
| Landing ring | 240 ms |
| Path illumination | The current hop lit statically |
| Residual trace | Persists until an *event* (acknowledgement or settling) — **temporal fading is an event, never a clock** |
| State-dependent intensity | Ladder L1 trace / L3 travel / L4 arming and resolution |
| Hover explanation | Every part answers "why" |
| Focus transition | The landing point is the `morph`'s shared element |
| Mobile | Rule + landing ring on the visible row; no cross-screen travel |
| TUI | `│` rule + spine glyphs, no motion |

### 25.3 Can the thread carry the emotional weight of an arc reactor?

**Yes, if three things hold [I]:**

1. **It is the brightest thing in the product.** Nothing else glows, so at L3/L4 its head should
   be the single highest-luminance element on screen — a few pixels of near-white against a still
   dark field. In the Ladder's terms that is the opposite of dim. PR-1 must test that the head
   reads as *light*, not as a line.
2. **It lands somewhere you care about.** The arc reactor is moving because it is Tony's heart.
   The thread is moving because it lands on *your* work, at the moment it changes.
3. **It accumulates.** One travel is a moment; the traces are a record (§25.4).

### 25.4 The day's light

At world scale, the residual traces across the constellation draw a true picture of what Archeus
touched today: **the day's light**.

- Static, opened on demand from Relations or Now's handover.
- Different every day, because the work is different.
- Brighter the more Archeus has actually done.
- Acknowledging the handover returns the constellation to calm.

This is Archeus's answer to the glowing core: the light is not a power source pretending to be
the system — it is the visible sum of what the system did. It needs only V1's existing link and
execution records for the hops V1 records, and P21 for the rest.

## 26. "Archeus Core" as visual identity — the centre of gravity, without a fake core

| Candidate | From the domain model? | Always present? | Carries state? | Verdict |
|---|---|---|---|---|
| A central orb | **No** — no Core object behind it | Yes | Only by pretending | **Rejected** (the JARVIS cliché; 12/13 repos) |
| The mark and its orbit | Yes — system presence (DNA-6) | Yes (chrome) | Present / working / needs you / disconnected; orbit per real batch | **System-scale centre** |
| The current mission | Yes — the unit of work | When work exists | Through its spine | **Work-scale centre** (via the spine) |
| The active thread | Yes — `Message.links`, decisions | Only when Archeus acts | Agency, consequence | **The signature**, not a centre — it *moves between* centres |
| The lifecycle spine | Yes — mission states | When work exists | Where the work is, whether it moves | **The visible form of the work-scale centre** |
| The Relations graph | Yes — the world | On demand | Context, causality | **World-scale centre** |
| The Attention system | Yes | When obligations exist | What you owe | A channel, not a centre (it must stay calm) |
| The conversation | Yes | Always | What was said | The *origin* of threads — where light starts |

**Answer [I].** Archeus's centre of gravity is **the work**, seen at three scales:

- **the mark** (system);
- **the active mission's spine** (work);
- **the constellation** (world).

The **conversation** is where light starts, and the **thread** is how light travels between them.
On Now, the centre is the state sentence over the active spines (the flow strip, main doc §8.3).
That gives a focal image as strong as an orb — a few lit spines under one sentence — and every
pixel of it is true.

## 27. The Archeus Hero Moment Matrix

Frequencies are estimates for an active single user [I], to be replaced by PR-6's local log.
Intensity uses the ladder (0–4). Every moment is skippable by any input (F-5).

| Event | Frequency | Desired emotion | Visual intensity | Motion | Sound-ready? | Reduced motion |
|---|---:|---|---:|---|---|---|
| **Handover**: first open after ≥ 4 h (K-1) | 1–3 / day | Calm authority, "here is where things stand" | **4** | The state sentence; then the changed rows' traces in one stagger, ≤ 900 ms | Slot: a soft arrival | All at once |
| **Plan arming**, significant (K-2) | 2–10 / day | Deliberate, committed, trust | **4** | Commit → thread travel to Execute → the station arms, ≤ 900 ms | Slot: commit | The station arms |
| Plan arming, routine (fewer than 3 tasks and not the mission's first approval; or more than 3 armings in 10 min, F-1) | 0–20 / day | Confirmation | 3 | Thread travel + landing | — | Instant |
| **Resolution**, significant, on screen (K-3) | 1–5 / day | Satisfaction, earned | **4** | Light runs back along the spine to Done; the halo releases; the result line, ≤ 900 ms | Slot: resolve | Instant ✓ + result |
| Completion, routine or off-screen | 5–50 / day | Informed | 2 | A-01; V1's toast if ≥ 10 s off-screen | — | Instant |
| **Causality path** (K-4) | On demand | Understanding, discovery | 3 (by nature) | Hop-by-hop travel ≤ 1.2 s; the path stays lit | — | The path appears lit |
| **The day's light** (§25.4) | ≤ 1 / day, on demand | Accomplishment, ownership | 3 | Static traces appear in one step | — | Same |
| Attention arrival | 0–20 / day | Calm urgency | 3, then changes form | A-08 once | Slot: alert (opt-in only) | Band |
| Failure | 0–10 / day | Clear, recoverable | 3 | A-01; the light goes out | — | Instant |
| **Emergency stop** | Rare | Control, certainty | 3 | Every halo and trace drops to L0 in one 160 ms step — the "power-down" | Slot: stop | Instant |
| Reconnect | 0–5 / day | Relief | 2 | Halos return in one 240 ms step | — | Instant |
| Entering a mission | 20–100 / day | Continuity | 3 | `morph` 320 | — | Cross-fade |
| The first thread ever (first install) | Once | Understanding the signature | 3 + a one-time caption ("This line shows what Archeus changed") | Normal travel; the caption stays until dismissed | — | Line + caption |

**Questions answered:**

- **Are four enough?** Yes, as L4. The benchmark's hero moments (boot, wake word, completion burst)
  map to handover, plan arming and resolution. The causality path is Archeus's own.
- **Missing?** Two non-hero additions earned their place:
  - the **emergency stop power-down** (L3, true, memorable);
  - the **first thread** caption (teaches the signature once).
- **Too frequent?** Plan arming is the risk, so it is gated by significance with F-1 demotion.
- **Genuinely spectacular:** resolution and plan arming, in that order.
- **Subtle:** handover — it is daily, so its drama is the stagger of information, not light.
- **Can repeated use reduce intensity?** Yes, through F-1 frequency demotion and F-3 once per
  absence.
- **Can the same event have different intensity by significance?** Yes. Plan arming and
  completion each have two to three tiers above.

## 28. The "alive" feeling, from real state only

JARVIS feels alive because things always move. Archeus should feel alive because **something real
is happening, and the interface knows it first**. The research supports six sources [R/I]:

1. **A heartbeat that is real.** The mark's orbit turns once per real output batch (≤ 1 per 5 s)
   and parks. Its rhythm *is* the system's rhythm — the Live Wire principle (E-48). When work
   stops, the heartbeat stops, and that is information.
2. **Responsiveness.** Every input answers within 100 ms (pointer affordance, A-09; instant
   focus). An interface that answers instantly feels alive without moving on its own.
3. **Specificity.** "Running 214 tests in Payments", "Searching code", "attempt 2 of 3". Visible
   intelligence is specific text and action figures (P21), not a shimmer — the spinner-verb
   complaint (E-44) is the counter-example.
4. **Anticipation.** JARVIS "anticipates informational needs" (E-72). Archeus does it with:
   - the action model's suggested next verb;
   - handover summaries;
   - the armed station;
   - the state sentence naming what needs you.
5. **Continuity across states.** Execution progress (the spine), background missions (the flow
   strip), connection (the mark solid or hollow), readiness ("Archeus is idle. Nothing needs
   you." is a living sentence too), and resource activity (last-used ages in the meta column).
6. **Liveness that admits silence.** "No output for 12 min" is more alive than a spinner, because
   it is true.

**No fake breathing:** an idle Archeus is still, and the stillness is the readiness signal (V1's
"it stops").

## 29. Voice as a future visual extension (informs V2-A1)

Nothing here is to be built now. It feeds V2-A1's design under ADR-0050. Evidence: E-74…E-77; the
reel 3 caption-first approach (E-69); 8/13 repos drive visuals from real audio, and the rest fake
it (E-68).

| Voice state | Signal (real) | Visual | Text (primary) | Reduced motion |
|---|---|---|---|---|
| Idle | — | The push-to-talk control at rest; nothing else | — | Same |
| **Listening** (PTT held) | Mic RMS per audio block, instant rise, ×0.8 fall, ≤ 60 Hz (E-77) | A level meter at the control, proportional to the measured level; runs **only while held** | "Listening" | Static "Listening" + a stepped level (no sweep) |
| Transcribing / processing | The request is in flight | Static; the live transcript text appears as it arrives | The transcript itself | Same |
| Thinking / working | Ordinary mission and planning states | **No voice-specific animation** — the normal state language (§5) | Planning: … | Same |
| **Speaking** (TTS) | The output's real amplitude (an analyser on the output, or a server envelope, E-67) | The same meter, driven by the output; the spoken text shown and synchronized (W3C NAUR REQ 7) | The response text | Text only |
| **Interrupted** (barge-in) | The user presses PTT during speech | Playback stops *immediately*; the meter switches to the mic; the unplayed part of the text is marked as not spoken (OpenAI truncate, E-75) | "Stopped — listening" | Same |
| Muted / permission denied | OS or browser state | A static mic glyph; red only if the user must act to fix it | The reason | Same |
| Error | — | Text; no pulse | The reason | Same |
| Wake word | — | **Not planned.** Push-to-talk gives control, avoids VAD failures and "feels snappy" (E-75); users ask for hold-to-talk (E-75) | — | — |

**How voice connects to the visual language:**

- A spoken turn becomes a conversation turn, so **the thread starts from it** like any other
  intent.
- Captions and the transcript are the primary channel.
- Motion never encodes a state by tempo alone. Alexa's fast vs slow purple pulse is the
  counter-example (E-74).
- The meter is a level, not an orb. Voice gets no face, no particle sphere and no humanoid.

## 30. Decisions recorded and what Part II changes

**Recorded by the user, 2026-10-04** (rulebook §46.4):

- **V-D1:** yes — rulebook §27 now says it.
- **V-D2:** yes.
- **V-D3:** yes, as a design rule.
- **V-D4:** yes, prototype-gated.
- **V-D5:** yes, prototype-gated, with no global type increase before PR-4.
- **S-1, S-2, S-3:** V1 corrections.

§18.1's table now reads as decided, on those terms.

**What Part II changes in Part I:**

- §6.2's five intensity names become the ladder of §23 (L0 Calm … L4 Hero), with attention as a
  channel rather than a level.
- The hero matrix (§27) supersedes §7's list as the candidate set:
  - same four L4 moments;
  - plus the e-stop power-down and the first-thread caption at L3;
  - plus significance tiers for plan arming and completion.
- §16.2's signature is unchanged and sharpened:
  - the thread is the brightest thing in the product at L3/L4;
  - it accumulates into the day's light.
- The centre of gravity is answered (§26): the mark, the spine and the constellation. No orb.

The governing document is now [ARCHEUS_V2_UI_ARCHITECTURE.md](ARCHEUS_V2_UI_ARCHITECTURE.md).
