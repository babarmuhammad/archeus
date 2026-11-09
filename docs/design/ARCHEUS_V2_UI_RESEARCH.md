# Archeus V2 UI — Research, V1 Assessment, Visual Language, Interaction Model and Roadmap

**Status: RESEARCH — PROPOSED, nothing decided.** Every recommendation below is a proposal for
the user's decision. Nothing here amends the V1 rulebook
([ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md](ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md)),
an ADR, a gate or any V1 phase. Where this document and an approved V1 document differ, the V1
document governs V1 and this one is a proposal for after it. "Do not proceed on inferred approval"
(rulebook §0, R5) applies.

Date 2026-10-04. Branch `archeus-v1-rearchitecture` at `cb11480` — P19 complete, **R13 passed**
after its correction pass, P19.5 not yet exited (manual checks and the user's sign-off owed,
r13-design-review §6). Nothing in the product, the tests, CI or the dependencies was changed to
produce this document. Its evidence is
[../research/2026-10-v2-ui-reference-study.md](../research/2026-10-v2-ui-reference-study.md)
(cited as `E-n`); this document is meant to be readable without it.

**Addendum.** Visual impact, the motion language, depth, living state, hero moments and the
visual signature are covered in [ARCHEUS_V2_VISUAL_DIRECTION.md](ARCHEUS_V2_VISUAL_DIRECTION.md).
That addendum proposes changes to §7, §10.3 and §12 of this document. It lists them in its §18.2
and does not apply them here. Its Part II benchmarks Archeus against JARVIS-style interfaces.

**Governing document.** The architecture V2 implementation will follow is
[ARCHEUS_V2_UI_ARCHITECTURE.md](ARCHEUS_V2_UI_ARCHITECTURE.md), written 2026-10-04 from both
documents. Where it and this research differ, the architecture document is the later word. It
remains subject to the user's approval of its proposals.

**Tags.** **[A]** an Archeus fact (code, a decided document, a capture). **[R]** a research fact
(E-n). **[I]** inference or recommendation.

## Contents

1. Research report (executive summary)
2. Baseline: what V1 is, and what V1 phases still own
3. V1 UI assessment (deliverable 2)
4. External reference study — the distilled lessons (deliverable 3)
5. Technology evaluation (deliverable 4)
6. V2 interaction philosophy and model (deliverable 6)
7. V2 visual language, including the motion language (deliverable 5)
8. Spatial UI, candidate by candidate
9. Performance and accessibility constraints
10. V2 UI opportunity matrix and buckets (deliverable 8)
11. V1 → V2 boundary (deliverable 7)
12. Proposed V2 UI roadmap (deliverable 9)
13. Recommended next architecture and design documents (deliverable 10)
14. Method, evidence and gaps

---

## 1. Research report — executive summary

**The verdict in one paragraph.** V1's UI is a sound, disciplined base, and V2 should not replace
its language. Its quiet-instrument rules (fixed state colours, no hue accent, the thread as the
one signature, motion only from real events, an idle page that runs zero frames, a Canvas 2D
graph with an authoritative list mirror) are the same rules the strongest external references
arrived at independently: the dark cockpit, Geist's status dot, Temporal's "only pending things
move", Linear's "don't compete for attention you haven't earned", calm technology. **What V1 lacks
is not visual richness; it is a model of the mission as an object with a lifecycle, and a queue
organised by what the user owes.** Today a mission is a state word plus a status line on every
surface; Attention is Core's order, ungrouped; and liveness is binary (running or not) with no
way to tell "working" from "silent for ten minutes". V2's job is to make **where each piece of
work is, what it is waiting for, and whether it is still alive** legible at a glance — with the
V1 vocabulary — and to stop there.

**Ten findings.**

1. **Keep the V1 language.** Every external reference that handles agent work well (E-10, E-14,
   E-19, E-26, E-34) converges on V1's core rules. None of the supplied visual references
   justifies changing them.
2. **The mission needs a lifecycle spine** — one static, segmented figure (understand → plan →
   approve → execute → verify → review → done) drawn from Core's existing states, reused in rows,
   cards, the inspector, the phone and the TUI. It costs zero frames and needs no Core change
   (§6.3 P-1). This is the single largest V2 legibility gain.
3. **Attention should be grouped by obligation** (decide / review / unblock), with acknowledge
   separate from resolve and snooze that wakes on a condition (E-10, E-25, E-27, E-33). The
   grouping is client-side; acknowledge and snooze need Core records.
4. **Liveness must become explicit.** V1's per-output pulse is more honest than a spinner — a
   stalled execution stops pulsing — but nothing says "quiet for 12 min". V2 adds a Core-derived
   liveness reading (active / quiet since / unresponsive), never a loop (E-14, E-26; §7.4).
5. **Huw Prosser's site has no motion, no depth and no WebGL** (E-1). Its identity is restraint: a
   character grid, tabular right-aligned meta, hierarchy by weight, one border, instant hover.
   That is a lesson Archeus can use (§7.1); the brief's premise that it studies depth and motion
   does not hold.
6. **Thinking Orbs: inspiration only.** The state vocabulary and the per-size tuned figures are
   good ideas; the perpetual per-instance loop, the missing announcement and the "thinking"
   animation itself are what the rulebook already rejects (§27: "thinking orb / shimmer for model
   reasoning"). Translate the idea into **static state figures**; build no orb.
7. **Anime.js: reject as a dependency.** Everything Archeus animates is a finite transform or
   opacity step owned by a registry with deterministic `renderAt(t)`; CSS and WAAPI (now Baseline
   with `linear()` springs, `@starting-style` and same-document View Transitions) cover it at
   0 KB, while Anime.js costs 13–44 KB gzip, has no built-in reduced motion and its own clock
   (E-3, E-5). The legacy GUI already used it and V1 deliberately left it.
8. **Three.js: reject for the V2 app.** The research does not support mono 3D for graph
   comprehension (E-8), the minimum bundle is 133 KB gzip (E-6), and Archeus's own legacy record
   in the Qt shell is a 250 ms p95 frame collapse, an ANGLE bug and a scene users switched off
   (E-6). Keep Canvas 2D; name a WebGL 2D escape hatch (sigma-class, 38 KB) with a measured
   trigger; re-scope V1.x-3D to a research spike with kill criteria.
9. **Relations is the right place for spatial work, but as a query launcher, not a destination**
   (E-24, E-30, E-31): ego graph at depth 1 by default, stable layout, saved views, semantic zoom
   tiers, and the causality path once P21 records it. 2D is sufficient; nothing about the
   candidate surfaces needs 2.5D beyond the depth tiers V1 already draws.
10. **V1 needs almost nothing.** The worthwhile V1 corrections were found and decided by R13
    (§8 of that review); this research adds **one** low-risk correction (the approval card's task
    table on a phone) and two decision requests (§11.2) — all three since decided by the user as V1
    corrections (rulebook §46.4, 2026-10-04). Everything else waits for V2 — and the
    V2 UI cannot start before the V1 phases that own its inputs (P20 push, P21 activity record
    and causality, P22 tints) have landed.

**What V2 should feel like to operate:** handing work to a capable colleague at a calm desk.
You hand work over in words; you are told only what needs you, in the order you owe it; at a
glance you can see where each piece of work is in its life and whether it is still moving; and
any change can be traced to what caused it. The interface is dark and still while nothing
happens, and every light on it means something (§6).

---

## 2. Baseline — what V1 is, and what V1 phases still own

### 2.1 V1 as built (verified at `cb11480`) [A]

- **Stack.** React 19.3 SPA, Vite 8, TypeScript 5.9. Runtime dependencies: `react`, `react-dom`,
  `qrcode-generator`. No router, state, CSS, graph or animation library. Served from the wheel;
  PWA with a shell-only service worker. One SSE stream per browser, ids-only frames, re-read on
  every frame (ADR-0009).
- **IA (ADR-0014).** Now, Work, World, Control + Attention + command bar, from one table
  (`tokens/navigation.json`) that drives sidebar, rail, phone tabs, keys and the TUI. The graph
  is a mode of World. Inspectors open over any destination (`#/o/<kind>/<id>`), resizable
  360–560 px.
- **Shell.** Mark + orbit presence + operations strip ("N running · N needs you · N clients",
  freshness, Pause all / Resume all, Emergency stop behind a confirm) on every page.
- **Now.** State sentence; automations line; Needs you (top 3, full Attention cards); Happening
  now; Since you last looked (digest); Upcoming; Recent decisions; Live map (≥ 1000 px, ≤ 40
  nodes); the conversation with typed live cards and the T1 thread line.
- **Mission inspector.** Seven tabs: Outcome, Plan (waves, versions, plan edit while PROPOSED),
  Now (the mission's own conversation + running tasks), Evidence, Why, Timeline (linear event
  log), Relations. **No lifecycle visualisation:** the mission is a state badge plus a status
  line (`present.ts statusLine`). The only stepper in the app is the Ideas path (read-only, D-11).
- **Attention.** Core's order, no client grouping; approval card with the action table, why, if
  approve / if reject, expiry, covers, Details, PIN step-up, request changes.
- **Graph.** Canvas 2D, deterministic layout run once (seeded mulberry32, 120 iterations), static
  + dynamic layers, LOD dots above 250 nodes, DPR ≤ 2, 19 shapes, confidence tiers by dash, halo,
  cored live node, hull, depth tiers, travelling marker (≤ 8), pulse (≤ 12), legend with toggles,
  expand/collapse-all, impact view, static project cage, full keyboard walk, screen-reader mirror;
  below 600 px the Relations list.
- **Motion.** One registry (`tokens/motion.json`, 16 entries, 15 built; A-17 activity chip
  approved, not built), one rAF caller that parks, `renderAt(t)` timeline with no replay, CSS
  finite keyframes of transform/opacity only. Idle runs zero frames (gated e2e).
- **Appearance (ADR-0044).** Theme System/Dark/Light, contrast System/Standard/High, motion
  System/Reduced; forced colours always win; applied before first paint.
- **Offline.** A read-only Now from the four last Now reads in IndexedDB, labelled "as of",
  no commands.
- **TUI.** Pure Python on the in-house renderer; same tables, cache, presentation and copy;
  glyph + word per state with an ASCII fallback; no motion; `│` changed marker; no graph.
- **Desktop shell.** PyQt6 QtWebEngine window + tray (Open, Pause all, Emergency stop with a
  native confirm, Quit).
- **Gates.** Contrast and ΔE floors, the motion registry and idle invariant, no
  `filter`/`backdrop`/blend, copy/id gate, axe, overflow at 390–1920 px, parity fixtures with the
  TUI, mutation-verified. **No JS/CSS bundle-size budget exists.**

### 2.2 What V1's remaining phases already own (V2 must not re-own them) [A]

| Item | Owner | Record |
|---|---|---|
| OS notifications and mobile push (approval required, e-stop) | **P20** (Q-B5) | rulebook §17 |
| Credential/remote-access review incl. the mobile e-stop PIN, desktop-shell device rows | **P20** | R13 §3 "Not findings", §5 |
| Activity chip — the "current action" of an execution (A-17), needs a Core record first | **P21** | rulebook §46.2 |
| Trace view, replay and scrub "as of" (classes only, two clocks) | **P21** | rulebook §12, §26 |
| Causality marker execution → produced object (Q-B1), general event cause | **P21** | rulebook §30 |
| Server-side search for the command bar (D-12) | **P21** | rulebook §46.1 |
| Upcoming step 2: schedules and `next_run` (Q-B2) | **P21** | ADR-0030 |
| `live_work` in `/v1/status`; account consumption views | **P21** | plan §31.1 P21 |
| Thread tints and the curated tint list | **P22** | rulebook §46.2 |
| People / organisation nodes; the Resources UI for every ADR-0041 field | **P22** | rulebook §13, §46.1 |
| PWA install, physical touch, Windows Terminal/conhost, 60 fps at 1,000 nodes on an iGPU | **P18 closure / P23** | rulebook §26 R18 |
| Website DNA mapping, screenshots | **P25** (Q-V6) | rulebook §26 R19 |
| Alt+1/2/3 and Alt+J replacing Ctrl+1/2/3 and Ctrl+J, verified before P26 | **before P26** | rulebook §46.3 |
| Compact density | **V1.x** | rulebook §7.2 |
| 3D mode, inner-web counter-rotation, system nodes | **V1.x-3D** | ADR-0016, ADR-0030 |
| Voice, desktop presence, browser/desktop capabilities | **V2-A0…A5** | ADR-0050, ARCHEUS_V2_ASSISTANT_LAYER.md |

V2 UI work in this document is called **V2-U** to keep it distinct from the assistant layer's
**V2-A**. Every V2-U production phase starts after P26, like V2-A (assistant-layer §2).

---

## 3. V1 UI assessment

Categories, as the brief defines them: **KEEP** · **V1 SMALL IMPROVEMENT** · **V2 REDESIGN** ·
**V2 ENHANCEMENT** · **DEFER** · **REJECT**. Evidence is the V1 code, the R13 captures
(1440 × 900 dark/light/high contrast, 390 × 844 touch, offline cold start) and R13's findings.

### 3.1 Surface scores

Scored 1 (poor) – 5 (excellent) for the V1 scope, not against V2 ambitions. "Legible" = the
surface answers its question at a glance; "Alive" = real activity is visible without noise;
"Dense" = space is spent on content; "A11y" = keyboard, screen reader, contrast, reduced motion;
"Phone" = the 390 px form.

| Surface | Legible | Alive | Dense | A11y | Phone | One-line reading |
|---|---|---|---|---|---|---|
| Shell + strip | 4 | 4 | 4 | 5 | 4 | Persistent, quiet, correct; strip text is small |
| Now | 3 | 4 | 3 | 5 | 2 | Right blocks in the right order; full approval cards and the digest flood push live work below the fold (R13-03) |
| Conversation + cards | 4 | 4 | 4 | 4 | 3 | Live cards and the thread line work; copy rough edges (R13-05…08) |
| Mission inspector | 3 | 3 | 3 | 5 | 3 | Complete but flat: state word + status line, no lifecycle shape |
| Work | 4 | 3 | 2 | 5 | 4 | Correct grouping; at 1440 px two rows over ~700 px of nothing |
| Attention | 3 | 3 | 3 | 5 | 2 | Every fact present; the safety-critical card speaks least plainly (R13-04) and crushes on a phone |
| Relations list | 4 | 4 | 4 | 5 | 4 | The a11y authority; source column decided out (R13-11) |
| Graph | 4 | 4 | 4 | 4 | n/a | A disciplined Canvas 2D instrument; default view not yet an ego/query launcher |
| Live map | 2 | 4 | 2 | 4 | n/a | Two nodes in a 320 px box plus three lines of key help at typical counts |
| Execution inspector | 3 | 3 | 3 | 5 | 3 | Output tail + checkpoints; no sense of where the time went |
| Control → Resources | 3 | 2 | 3 | 5 | 3 | Correct forms; no rolled-up health |
| Control → Appearance | 5 | — | 4 | 5 | 4 | Exactly the right three choices |
| Offline snapshot | 4 | — | 4 | 4 | 4 | After R13-02, answers "what needs me"; frames time correctly |
| TUI | 4 | 3 | 4 | 4 | — | Strong parity; Now header still the pre-ADR-0027 presence line |

### 3.2 Classification by area

| # | Area | V1 as built | Class | Reason |
|---|---|---|---|---|
| A1 | IA: Now / Work / World / Control + Attention + command bar | ADR-0014, one nav table | **KEEP** | Maps the mental model; one table drives every client; changing it would ripple through SPA, TUI, phone and tests for no demonstrated gain |
| A2 | State vocabulary (presentation classes, glyph + word, 6 state colours) | `presentation.json`, ΔE ≥ 20 gates | **KEEP** | The heart of the system (DS §10); every reference with a good status model has ≤ 6 hues (E-20, E-26) |
| A3 | No hue accent; neutral primary; thread ink as focus | DS §3, ADR-0028 | **KEEP** | Independent confirmation from Linear's 2026 refresh and Huw Prosser's monochrome (E-1, E-27) |
| A4 | Motion registry, idle invariant, two clocks, no replay | ADR-0024, `motion.json`, `timeline.ts` | **KEEP** | The best-specified motion system found anywhere in this research; Geist and Temporal reach the same rule with less rigour |
| A5 | The thread (T1 line, T2 rule) | ADR-0026 | **KEEP** (V2 ENHANCEMENT in §7.6) | R13's template test names it; V2 extends where it appears, not what it is |
| A6 | Mark, orbit presence, favicon state, strip | ADR-0027 | **KEEP** | Presence always visible and always quiet; calm-technology periphery (reference study §4.9) |
| A7 | Pause all / Emergency stop placement and semantics | strip, Work, tray, Control, chat | **KEEP** (review in V2, §6.3 P-13) | E-34 supports an e-stop outside the main UI (the tray); the always-visible red-outlined strip button is a V2 question, not a defect |
| A8 | Now block order and the ≤ 7 cap | DS §11 | **KEEP** | The hierarchy is right (rulebook §7.1) |
| A9 | Now: full approval cards inline in Needs you | `AttentionView` limit 3 | **V2 REDESIGN** | At 1440 px one approval card is ~490 px tall and pushes Happening now below the fold; compacting a safety-critical card is not a small change (§6.3 P-2) |
| A10 | Digest message flood | R13-03 | **V1 (decided, R13 §8)** | "One N new messages row" — already the user's decision; listed so V2 does not re-own it |
| A11 | Live map | `GraphView` map mode | **V2 REDESIGN** | At typical counts (1–5 live missions) a 320 px canvas carries less than a row would; reconsider as a lifecycle/flow strip or size it to content (§8.3) |
| A12 | Conversation → card → action | ADR-0015, `Now.tsx` cards | **KEEP** model, **V2 ENHANCEMENT** | Cards are live references, never copies — correct. V2 adds the spine to cards and an action model (§6.3 P-4) |
| A13 | Mission lifecycle representation | badge + status line; Timeline is a flat log | **V2 REDESIGN** | No surface shows where a mission is in its life (§6.3 P-1) |
| A14 | Mission inspector's seven tabs | `navigation.json` | **KEEP** structure, V2 ENHANCEMENT | The tabs are the right partition; V2 adds a header spine and a compact timeline mode (E-19) |
| A15 | Attention ordering and grouping | Core order, ungrouped | **V2 REDESIGN** | Obligation groups, acknowledge ≠ resolve, snooze with condition (§6.3 P-2) |
| A16 | Approval card copy (rule ids, ISO time, TUI list repr) | R13-04 | **V1 (decided, R13 §8 recommended)** | Already recorded |
| A17 | Approval card task table on a phone | the four-column table crushes to "Cl / as / s", "Tar / ge / t" at 390 px (capture `p01_now`) | **V1 SMALL IMPROVEMENT** (§11.2 S-1) | Safety-critical card, phone is the approval device (rulebook §19), container-query stacking is an existing codebase convention |
| A18 | Work density and the empty right side at ≥ 1440 px | groups only | **V2 ENHANCEMENT** | Rulebook §7.2 named a plan rail ≥ 1440 px; not built; V2 does it with the spine (§6.3 P-9) |
| A19 | Pins (D-9), priority (D-14), row menu, ideas read-only (D-11) | built | **KEEP** | Decided by the user 2026-10-03 |
| A20 | Relations list as the authoritative accessible form | `Relations.tsx` + mirror | **KEEP** | No graph library offers keyboard or AT navigation (E-7); V1's mirror is ahead of the field |
| A21 | Graph renderer (Canvas 2D, layout-once, static/dynamic layers, LOD) | `graph/*` | **KEEP** | Matches the measured practical rule for ≤ 1–2k nodes (E-9) |
| A22 | Graph default view and navigation model | focus + depth 1/2, cap 500 | **V2 ENHANCEMENT** | Ego graph is already the default; V2 adds saved views, semantic zoom tiers, causality overlay (§6.3 P-6) |
| A23 | 3D graph mode | V1.x-3D (named) | **REJECT for the app** / DEFER as research (§5.2) | E-6, E-8 |
| A24 | Execution representation | state + output tail + checkpoints | **V2 ENHANCEMENT** | Liveness reading and a time-split strip (§6.3 P-3, P-7); both need Core records |
| A25 | Activity chip (A-17) | approved, not built | **DEFER → P21 (as recorded)** | Text needs a Core record |
| A26 | Resources (accounts, harnesses, capabilities, policies) | forms + route decisions | **KEEP** forms, **V2 ENHANCEMENT** health roll-up (§6.3 P-8) | A topology view would not answer a question the forms do not (§8.5) |
| A27 | Appearance: theme, contrast, motion | ADR-0044 | **KEEP** | Exactly enough; customisation beyond it is the skins/worlds lesson |
| A28 | Compact density | V1.x | **DEFER → V2-U1** | Fold into the V2 token pass (§7.2) |
| A29 | Thread tints | P22 | **DEFER (as recorded)** | — |
| A30 | Ambient effects, skins, worlds, glass, glow | rejected (§27, ADR-0017) | **REJECT** | Unchanged by any reference studied |
| A31 | Offline snapshot | read-only Now, "as of" | **KEEP**, **V2 ENHANCEMENT** (§6.3 P-11) | Read-only is right (E-33); V2 widens what is kept, not what can be done |
| A32 | TUI semantics, no motion, `│` marker | P17, R13-16 accepted | **KEEP** | The TUI must not imitate the SPA |
| A33 | TUI Now header ("Archeus · N missions active · N things need you") | pre-ADR-0027 line; no Upcoming / Recent decisions | **V1 SMALL IMPROVEMENT** (§11.2 S-3, decided 2026-10-04) | Whether ADR-0027's state sentence is a cross-client rule is not recorded |
| A34 | Command bar (palette, object actions, effect preview, cache-only) | D-12 | **KEEP**, **V2 ENHANCEMENT** action model (§6.3 P-4) | Server search is P21's |
| A35 | Toasts (D-8), no row insert/remove animation (§46.2 exception) | built / exception | **KEEP** | Decided |
| A36 | Live map key-help caption on Now | three lines of graph keys under a toolbar-less map | **V1 SMALL IMPROVEMENT** (§11.2 S-2, decided 2026-10-04) | Noise on Now vs. discoverability |
| A37 | Bundle-size budget | none exists | **V2-U0** (could land earlier at no product risk) | §9 |

---

## 4. External reference study — distilled lessons

Full entries, sources and evidence tags are in the reference study. This section keeps only
what changes a recommendation.

### 4.1 The supplied references

| Reference | What it really is | What Archeus takes | What Archeus does not take |
|---|---|---|---|
| **Huw Prosser** (E-1) | A Svelte document site: monochrome, one monospace face, tables as structure, tabular right-aligned meta, hierarchy by weight, one 1 px border, **no motion, no depth, no WebGL** | (1) a **meta column**: dates, counts, durations and freshness right-aligned in tabular figures, everywhere; (2) hierarchy by weight at near-constant size for dense lists; (3) structure "felt, not seen" — fewer separators, one border weight; (4) instant, transition-free hover is acceptable for frequent interactions (HIG: avoid motion on frequent interactions) | monospace for body text (Archeus is a reading tool; mono stays for ids, commands, numbers); personality in copy (ADR-0027 §5); CDN fonts (offline rule) |
| **Thinking Orbs** (E-2) | Canvas 2D dotted spheres, nine perpetual state animations, per-size tuned designs, static frame under reduced motion, `role="img"` without announcement, one rAF per instance | the idea that **each live state has its own figure**, and that **each size is drawn, not scaled** (§7.5 state figures) | the loop, "thinking" as an animation (rulebook §27; P16 §18.1 r8 "hidden reasoning never animated"), per-instance rAF, states Core does not record (searching, composing) |
| **Libraries.dev, rest** (E-2) | Border Beam, Gooey, Voice, Bot Avatars, Metal, Image | Voice's *principle* — a level meter that moves only with real microphone input — for V2-A1 push-to-talk | every implementation (§5.4) |
| **Anime.js** (E-3) | a capable choreography library, 13–44 KB gzip, its own clock, no built-in reduced motion | nothing (§5.1) | the dependency |
| **Three.js** (E-6) | the standard WebGL scene graph, 133–219 KB gzip, WebGPU still experimental | nothing for the app (§5.2) | the dependency; the site (`www/`) keeps its own scene, outside this scope |

### 4.2 The ten lessons from real products that change a recommendation

1. **Group by what the human owes** (E-10 Claude Projects: Ready for review / Waiting on you /
   Working / Landing / Idle / Resolved). → Attention and Work grouping (P-2, P-9).
2. **Status derived from activity, with a liveness rule** (E-14 Linear: six states from the last
   activity; ephemeral "currently doing" line; 10 s acknowledgement or "unresponsive"). → P-3.
3. **Only pending things move; line style says "not final"** (E-19 Temporal; E-26 Geist). →
   Archeus already moves only on evidence; adopt dashed = not final for the spine (§7.3).
4. **Needs-you changes position and area, not just an icon** (E-16 Warp user complaints; E-34
   ATC research). → a static attention band (§7.7).
5. **Silence is a feature** (E-11 Codex auto-archives empty runs; E-35 push only on action
   required). → no Attention item without an action; automation runs with nothing to report
   never surface (already true for toasts, D-8).
6. **Approvals never time out into action** (E-15 Devin's 30 s auto-proceed is the
   anti-pattern). → Archeus already expires approvals into nothing; make it a written rule.
7. **Acknowledge ≠ resolve; snooze takes a condition** (E-25 Sentry, E-27 Linear, E-33 Open MCT).
   → P-2, needs Core.
8. **A graph earns its place as a query launcher, local and stable** (E-24 Honeycomb, E-30
   Obsidian, E-31 Nx/Backstage). → P-6.
9. **Split where the time went** (E-22 Inngest). → P-7, needs Core.
10. **One action model everywhere** (E-27 Linear single-key verdicts, E-28 Raycast Enter /
    Ctrl+Enter / palette with shortcuts printed, E-37 lazygit/btop hint = hotkey). → P-4, P-12.

### 4.3 What Archeus explicitly does not copy

Kanban drag that starts work and spends quota (E-18); auto-proceed timers (E-15); "the model
decides when to push" (E-35); follow-the-agent by default (E-17); two parallel surfaces (E-12);
global hairball graphs (E-30); ten state hues (E-20); full event history as a default view (E-19);
user-composable dashboards (E-33); sci-fi HUD styling (E-34); avatars and personas (E-2, E-1).

---

## 5. Technology evaluation

### 5.1 Anime.js — **REJECT** (as a dependency, in every surface)

| Question | Answer |
|---|---|
| What would it do for Archeus? | Timelines, stagger, springs, draggable, SVG line drawing, layout animation |
| What does Archeus actually animate? | 15 built motions, each a finite transform/opacity step or a canvas draw at `renderAt(t)`, capped, never replayed, refused under reduced motion (§2.1) |
| Timelines / stagger | Not needed: the registry forbids choreography that is not tied to one event (rulebook §21); a stagger across a list is the "page that blooms" effect the legacy GUI used for decoration |
| Springs | CSS `linear()` (Baseline 2026-06) bakes a spring into keyframes at 0 KB, on the compositor (E-5) |
| SVG drawing (`createDrawable`) | `stroke-dashoffset` with a CSS keyframe; the thread line is already a 600 ms CSS draw |
| Draggable | Not wanted: drag-to-move (rulebook §27) and drag-as-command (E-18) are rejected; reprioritise is a number (D-14) |
| Layout animation | Not wanted in V1 (row insert/remove exception, §46.2); if V2 reopens it, same-document View Transitions are Baseline and Chromium 140 has them |
| Clock and determinism | Anime runs its own engine clock; the registry needs every visual to be a pure function of (event, presentation time). Driving it from `graph/loop.ts` via `useDefaultMainLoop=false` is possible (the legacy GUI did it) but makes a second animation model to test |
| Reduced motion | None built in (E-3); every call site would need a scope — the registry already does this centrally |
| Cost | 13.3 KB gzip for `animate` alone, 44 KB whole; V1 adds 0 KB per motion |

**Alternatives (adopt as needed, no dependency):** CSS keyframes + transitions (as built), WAAPI
for any motion that needs `.finished` or programmatic cancel, `linear()` for spring-like easing,
`@starting-style` for enter, same-document View Transitions for layer changes (DEFER, §7.4).
**Motion (motion.dev)** is the one library with reduced motion by default (E-4); it is still a
second animation model and is **not recommended** either, but it is the answer if a future V2
surface genuinely needs React presence/layout animation at scale.

**Wrap behind an abstraction?** The abstraction already exists: `motion.json` + `timeline.ts` +
`Loop.animate(id)`. V2 extends that (§7.4), not a library.

### 5.2 Three.js — **REJECT for the V2 app; INVESTIGATE (time-boxed) only as the re-scoped V1.x-3D spike**

| Candidate surface | 3D useful? | Verdict |
|---|---|---|
| Relations / knowledge graph | No: mono 3D reduces path-tracing and spatial-memory performance (E-8: Cockburn & McKenzie; Kotlarek 2D better for spatial memory); the studied 3D gains need stereo + head-coupled motion | 2D |
| Mission topology / plan DAG | No: a plan is a short layered DAG; layered 2D or a list is exact | 2D / list |
| Execution history | No: a time axis is 1D | strip / timeline |
| Resource topology | No: ≤ tens of objects; forms + a route diagram answer every question | forms |
| Dependency visualisation | No: a path is a sequence; text + 2D highlight | 2D |
| System state overview | No: dark-cockpit rule — overview is the strip and Now | DOM |

Why not, in Archeus's own terms:

- **Comprehension.** "No unjustified 3D" (Munzner); Yoghourdjian 2021: path-finding fails above
  50–100 nodes in any node-link diagram, so the cure at scale is aggregation and filtering, which
  3D does not supply (E-8).
- **Cost.** ≥ 133 KB gzip for an empty scene (E-6), against a client whose whole runtime is React
  plus a QR encoder.
- **Platform.** WebGPU is experimental in three and undocumented in Qt WebEngine; Archeus's own
  Qt record includes a 250 ms p95 frame collapse from scene cost, an ANGLE compositing bug, and a
  flag (`--use-angle=gl`) that breaks WebGL on Intel UHD (E-6).
- **Accessibility.** A canvas is opaque; V1 already owns the parallel DOM (mirror), so 3D adds a
  camera-orientation problem to a solved one.
- **Product history.** The legacy three.js stage was judged overstimulating and switched off by
  both users; ADR-0016 deliberately carried none of it.

**Re-scoping V1.x-3D (proposed amendment to ADR-0016/ADR-0030 wording, for the user).** Keep the
name, change the content: a **research spike** with a written hypothesis ("an orbitable 3D view
of a project's knowledge clusters lets a user answer question Q faster than the 2D view"), a
measured task study on real project graphs, the Qt shell on an integrated GPU, and kill criteria
(no measurable task gain → closed; any idle frame → closed; > 1 MB of new JS → closed). No
product code until it passes. The website keeps its own scene (Q-V6, P25).

**The real escape hatch is WebGL 2D, not 3D.** If V2 Relations ever needs > ~5–10k drawn edges or
continuous layout, a sigma-class WebGL 2D renderer (sigma 3 + graphology, 38 KB gzip, MIT, Canvas
labels) fits (E-7, E-9). Trigger it only by measurement on the 1,000-node fixture and a real
corpus (§9); the mirror stays.

### 5.3 Thinking Orbs — **INSPIRATION ONLY**

| State | Orb behaviour | Archeus translation | Allowed motion |
|---|---|---|---|
| `working` | particles orbiting, perpetual | **active** (●): static figure; one 240 ms pulse per batch of real output (A-02, row-pulse) | event-driven only |
| `searching` | meridian sweep | none — Core records no "searching" state; if P21's activity record carries an action kind, a static figure per kind (§7.5) | none |
| `solving` / `weaving` ("planning" in the demo) | bands / braid | **planning** (◌, thinking violet): static figure + specific text ("Planning: reading Monday's notes") | none — hidden reasoning is never animated (rulebook §27) |
| `listening` | waveform | **V2-A1 push-to-talk only**: a level meter driven by the real microphone level while the user holds the key | proportional to real input, stops on release |
| `connecting` | constellation wiring itself | **reconnecting** banner + hollow presence node | none |
| `composing` | ribbon | none | none |
| `breathing` ("thinking") | ring morph | **rejected by name** | — |

Adopted: per-state figures and per-size tuning. Rejected: the component, every loop, the missing
announcement (V1's `role=status` strip and polite region are the correct pattern).

### 5.4 Libraries.dev effects, individually

| Effect | Does it solve an actual Archeus UI problem? | Verdict |
|---|---|---|
| **Thinking Orbs** | Partly — "what state is it in" — and V1 already answers it with glyph + word; the figure idea helps at 20 px | **Inspiration only** (§5.3) |
| **Border Beam** | Would mark "this card is live". V1 marks live work with the halo and the row pulse. The beam animates a paint property under `filter: blur()`, loops, and has partial reduced motion; it tears the Qt surface by the repo's own measurement | **Reject** |
| **Gooey** | Morphing shapes between states. No Archeus problem is "the transition between two shapes"; SVG blur filter | **Reject** |
| **Voice** | Yes, but only for V2-A1: showing that the microphone hears you while push-to-talk is held. The filter warp and the "processing" ping-pong loop are rejected; a plain level bar is enough | **Inspiration for V2-A1** (principle only) |
| **Bot Avatars** | No — avatars and personas are rejected (rulebook §27; agents are not the primary abstraction, ADR-0043) | **Reject** |
| **Metal** | No — WebGL2 shader on buttons; decoration | **Reject** |
| **Image** | No — Archeus generates no images; three.js peer; no reduced motion found | **Reject** |

### 5.5 Other technologies considered

| Technology | Verdict | Where / why |
|---|---|---|
| CSS keyframes, transitions (transform/opacity) | **Keep** | as built |
| WAAPI | **Adopt where needed** | programmatic cancel / `.finished` for registry motions; compositor-run |
| CSS `linear()` | **Adopt** | spring-feel easing for spatial motions without overshoot on effects (Material 3 rule) |
| `@starting-style`, `transition-behavior: allow-discrete` | **Adopt where needed** | enter states for dialogs/sheets instead of keyframes |
| Same-document View Transitions | **DEFER (V2-U6)** | inspector/sheet layer changes; only if it replaces keyframes 1:1, registered, reduced-motion off |
| Scroll-driven animations | **Reject** | not Baseline (Firefox), and nothing in Archeus should move because you scrolled |
| sigma 3 (WebGL 2D) | **Named escape hatch** | §5.2, only on a measured trigger |
| d3-force / d3-dag (layout only) | **Investigate in V2-U5** | layered layout for plan DAGs and causality paths; tiny, MIT; V1's own layout may suffice |
| ELK.js | **Reject** | 433 KB and EPL/GPL licence |
| cytoscape, G6, reagraph, cosmos, force-graph | **Reject** | size, no AT story, or non-commercial licence variants (E-7) |
| Data Navigator (research toolkit) | **Read, do not adopt** | confirms the mirror pattern; V1 is already there |

---

## 6. V2 interaction philosophy and model

### 6.1 What should Archeus feel like to operate?

Candidates, judged against what Archeus is (a persistent layer that runs missions on the user's
behalf across harnesses and accounts, with approvals, verification and memory), not against
aesthetics:

| Direction | Fits | Breaks | Verdict |
|---|---|---|---|
| **Command center** | strip, keyboard-first, e-stop | invites dashboards and metric cards (rulebook §27 "instrument dashboard as home") | a component, not the model |
| **Intelligent workspace** | projects, knowledge, inspectors | drifts toward document/IDE features Archeus is not (it orchestrates harnesses, it does not edit code) | a component |
| **Mission control** | dark cockpit, attention by exception, handover, e-stop outside the UI | taken literally, a wall of telemetry | **the attention model** |
| **Conversational OS** | Core is addressed in words; directives resolve to the same governed verbs (ADR-0042) | chat as the container hides state in scrollback; V1 already decided conversation is primary *input*, not the only view (ADR-0015) | **the input model** |
| **Spatial knowledge/work graph** | Relations, impact, causality | a graph as home fails every evidence test (E-8, E-24, E-30) | **an inspection layer** (ADR-0016 already says so) |
| **Hybrid** | — | — | **chosen, with a name and an order** |

**Recommendation: the handover model.** A calm desk where you hand work to a colleague and are
handed back only what needs you.

1. **You hand work over in words** (conversation = input; every directive becomes a governed
   verb, ADR-0042).
2. **The desk is dark while things are fine** (dark cockpit; V1's idle invariant).
3. **What needs you comes to the top, in the order you owe it** (obligation groups; position and
   area, not a badge alone).
4. **Every piece of work shows where it is in its life and whether it is still moving** (the
   lifecycle spine + liveness).
5. **Every change can be traced to its cause** (the thread; P21 causality; Relations as the
   query launcher).
6. **You can always stop everything from outside the page** (tray, strip, phone).
7. **You can leave and come back** (handover summaries, offline "as of", phone triage).

The unit is the **mission** (ADR-0004); the conversation is how you start and steer it; the
inspector is how you verify it; Relations is how you explain it.

### 6.2 Interaction rules (proposed V2 design rules)

- **IR-1 Obligation first.** Any list of work orders by what the user owes before recency.
- **IR-2 One spine.** A mission's place in its lifecycle is drawn by one primitive everywhere it
  appears, at the size of its container.
- **IR-3 Evidence-proportional liveness.** Motion only on real output; silence is shown as text
  with its age, then as a state when Core says so. Never a spinner standing in for evidence.
- **IR-4 Actions are named verbs with stated consequences**, reachable three ways (button, key,
  palette), identical in the TUI, never by drag or swipe alone.
- **IR-5 Silence into nothing.** No approval, timer or snooze ever turns into action without a
  person (written rule; matches V1 behaviour).
- **IR-6 Acknowledge is not resolve.** Seeing an item and dealing with it are two verbs.
- **IR-7 Graphs answer questions.** Every spatial view opens from a question (what does this
  affect, how did this happen, what is near this) and returns to a list.
- **IR-8 Same meaning, own form.** Every client keeps the vocabulary; layout, density and motion
  adapt (DS §1.6, unchanged).

### 6.3 The V2 proposals (P-1 … P-14)

Each states the V1 baseline, the proposal, the data it needs and whether Core must change.

**P-1 Mission lifecycle spine** (V2 REDESIGN of A13; Core: none).
- *Baseline:* state badge + status line; Timeline is a flat event log.
- *Proposal:* one primitive drawing seven stations — **Understand · Plan · Approve · Execute ·
  Verify · Review · Done** — mapped from Core's existing mission states (CREATED…REASONING →
  Understand; PLANNING/REPLANNING → Plan; APPROVAL_REQUIRED/APPROVED → Approve; EXECUTING/RESUMED
  → Execute; VERIFYING → Verify; REVIEWING → Review; COMPLETED → Done; FAILED/CANCELLED/BLOCKED/
  PAUSED as a mark *on* the station where it happened).
  - Passed stations solid, current station filled in its state colour, future stations hollow
    (the "dashed = not final" rule, §7.3).
  - Loops are counts, not drawings: "replanned 2×", "attempt 3".
  - Three sizes, each drawn for its size (§7.5): **row** (7 × 6 px ticks, ~64 px wide, no
    labels), **card** (ticks + current label), **inspector header** (labelled, with the time spent
    at each station from the Timeline's own events).
  - TUI: `●●◆○○○○` with the ASCII fallback `**!....`, plus the station word.
  - Phone: the row form.
- *Text equivalent:* "Step 3 of 7: waiting for your approval. Planned once." Static: zero frames.
- *Why it is the largest gain:* it answers "where is this?" on every surface without reading, and
  it replaces three V1 ad-hoc forms (status line, "0 of 1 tasks done", Upcoming vs Happening
  confusion R13-13).

**P-2 Attention by obligation** (V2 REDESIGN of A9, A15; Core: acknowledge and snooze records).
- *Groups,* in order: **Decide** (approvals, clarifications, challenges) · **Review**
  (verification acceptance, reviews) · **Unblock** (account sign-in, suspended automation, drift
  needing a decision) · nothing else. No FYI group: an item with no action is not an Attention
  item (IR-5, E-11).
- *Each row:* what · why it asks (in words) · **then vs now** where Core has it (E-33: "approval
  expires in 3 h", "drift found on 2 files, now 5") · the primary verdict · the spine.
- *Compact on Now, full in Attention:* Now's Needs you shows each item as one row with its two
  verdicts and "Review details"; the full card (action table, policy, PIN) stays in Attention and
  the inspector. **The full card remains required before any approval whose class is destructive
  or deploy, or that needs step-up** — compactness never hides what will happen for those.
- *Verbs:* the V1 verbs, plus **Acknowledge** (seen; leaves the badge count, stays in the list)
  and **Snooze until** a condition (time, the mission changes, quota resets) — both need Core
  records and an ADR (§13). V1's badge = count of items that need you stays exact (R6).
- *Area, not icon:* a needs-you row carries a static `state.attention` tint ≤ 12 % (DS §3.1 already
  allows state row tints) — never a left rail (the left edge belongs to the thread, rulebook §41).

**P-3 Liveness** (V2 ENHANCEMENT of A24; Core: a liveness reading).
- *Baseline:* halo while a read says active (with hysteresis); one pulse per output batch; state
  word "Executing".
- *Proposal:* three readings, all from Core, never from a client timer guessing:
  **active** (output within the harness's expected interval) · **quiet** ("no output for 12 min",
  shown as text with its age once past a threshold Core supplies) · **unresponsive** (Core's
  liveness rule fired; presentation class *blocked* only if a person must act, otherwise
  *paused*-grey with the word).
- Consumes P21's `live_work` and the A-17 activity record ("Running tests in payments") as one
  ephemeral line per execution (E-14), replaced, never stacked.
- No loop, no spinner: the absence of pulses plus the age *is* the signal (IR-3, §7.4).

**P-4 Conversation and the action model** (V2 ENHANCEMENT of A12, A34; Core: none for the model;
X7 steering needs its own ADR).
- Cards carry the spine and the meta column; a card about a mission is that mission's live row in
  card form, never a second rendering of its state.
- **Action model:** every card and row has one primary verb (Enter), one secondary (Ctrl+Enter),
  and the rest in the palette with their keys printed (E-28); the TUI prints the same letters
  (`[A] Approve`). Destructive verbs are never primary.
- "What Archeus is doing now" is a single quiet line under the conversation header, fed by P-3
  (not a spinner, not narration of reasoning).
- Steering a running mission (X7) shows where the message lands: "queued — applies after the
  current step" (E-13). Needs X7's ADR.
- Out-of-scope findings become a "Propose a mission" card action (E-10), which is an existing
  verb (a new mission through Core), not a new mechanism.

**P-5 Handover summaries** (V2 ENHANCEMENT; Core: none for step 1).
- Per mission, "since you looked": the stations passed, what it produced, what it asks — composed
  from the digest and the Timeline, shown at the top of the mission inspector and on the phone's
  Now. Folds R13-03's message rows by construction.

**P-6 Relations as a query launcher** (V2 ENHANCEMENT of A22; Core: P21 causality for the path).
- Default = ego graph at depth 1 around the object you came from (already V1's behaviour); **saved
  views** ("this project's open work", "what this mission touched") as named, local view state.
- **Semantic zoom tiers** (§8.1): dot → glyph → glyph + label → glyph + label + spine, chosen by
  rendered size, not zoom alone (E-9 Hornbæk).
- Overlays answering questions: **What does this affect?** (built), **How did this happen?**
  (causality path from P21 Q-B1), **Where did this mission come from?** (origin: conversation,
  automation, idea, phone — an origin badge Core already partly records via `cause_chain`).
- A **minimap** only above a drawn-node threshold (~150) and only on the full graph.
- Stable layout across visits (V1 layout-once, kept); positions never re-run by themselves.

**P-7 Execution time split** (V2 ENHANCEMENT; Core: a per-execution timing record).
- One static strip per execution: **working · waiting for capacity · waiting on you · handing
  off** (E-22), from Core's events, with the meta column showing each duration. Answers "why is
  this slow" and feeds the cost story (ADR-0041, ADR-0047).

**P-8 Resource health roll-up** (V2 ENHANCEMENT of A26; Core: none if derived client-side from
existing reads; verify).
- One health per account/harness — **healthy · will recover · needs you** — with the list of
  reasons (E-21): "at ceiling, resets 16:05" is *will recover*, "signed out" is *needs you*. Forms
  stay the editing surface. No topology view (§8.5).

**P-9 Work density and the plan rail** (V2 ENHANCEMENT of A18; Core: none).
- Rows gain the spine and the meta column; compact density (§7.2); at ≥ 1440 px with the
  inspector closed, the selected mission's plan rail (rulebook §7.2's unbuilt target) fills the
  right side.

**P-10 Phone as the handover device** (V2 ENHANCEMENT; depends on P20 push).
- Phone Now = Decide group + handover summaries + strip. Approvals short-lived where P20 decides
  so (E-35). Swipe still only reveals (rulebook §19). No plan authoring on a phone (E-36).

**P-11 Offline as a fixed-time view** (V2 ENHANCEMENT of A31; Core: none).
- Keep read-only. Label the whole view like a fixed-time conductor ("Showing 14:02, not live",
  E-33). Optionally keep the inspector reads of the missions that were on Now (bounded, same
  security rules as B7) so their spine and summary read offline. Never interactive.

**P-12 TUI** (V2 ENHANCEMENT; Core: none).
- Spine in ASCII; obligation groups; the same verdict letters; `?` shows the keys of the current
  context (E-37); highlighted hint letters are mouse-clickable where the terminal reports clicks
  (btop). Still no motion.

**P-13 E-stop placement review** (decision for V2).
- The dark-cockpit rule (E-34) suggests the always-visible red-outlined strip button is louder
  than its frequency of use. Options: keep (V1), move behind the strip's menu with the tray and
  phone as the always-available paths, or keep on desktop and hide on narrow widths. A V2 design
  question, not a V1 defect.

**P-14 Voice modality UI** (V2-A1, not V2-U). The listening state, the transcript card with its
modality provenance (ADR-0050 §9, XR-7), and the push-to-talk level meter (§5.3) are specified by
V2-A1 and reuse this visual language.

### 6.4 Execution-state vocabulary for V2 (what the brief calls queued … completed)

All from existing presentation classes; nothing invented.

| Brief's word | Core reality | V2 presentation |
|---|---|---|
| queued | APPROVED, not started ("Approved — not started"); task waiting for capacity | ◇ approved, spine at Approve passed / Execute hollow; P-7 "waiting for capacity" |
| planning | CREATED…PLANNING, REPLANNING | ◌ planning, spine at Understand/Plan, specific text, **no motion** |
| waiting | APPROVAL_REQUIRED, AWAITING_* (on the user); BLOCKED not on the user | ◆ needs you (attention band) **or** ■ blocked with reason — never one word for both |
| approved | APPROVED | ◇ approved |
| executing | EXECUTING / RUNNING | ● active + halo + per-output pulse + liveness reading |
| blocked | BLOCKED, CONFLICT, LIMITED | ■ red **only when a person must act**; "will recover" reasons in text (P-8) |
| failed | FAILED, ENDED_ERROR | ✕ red, plain reason inline, raw under Details, no toast |
| completed | COMPLETED | ✓ done, spine complete; a toast only under D-8 |

---

## 7. V2 visual language

V2's language is **V1's, sharpened**. Nothing below changes a V1 token value; where a value is new
it is marked **new**.

### 7.1 Typography

- Families unchanged: Segoe UI Variable / system sans for text, Cascadia Mono / system mono for
  ids, commands and numbers. No web fonts (offline rule).
- Scale unchanged (display 28 only for the state sentence; title 20/16; body 13 desktop / 17
  phone; caption 12/13).
- **new — the meta column** (Huw Prosser, E-1): every row ends with right-aligned metadata in
  `caption` + `tabular-nums` (age, duration, count, freshness), in a fixed-width column per list
  so values align vertically down the list. It replaces inline "just now" text placed after the
  title.
- **new — hierarchy by weight in dense lists:** row titles 13/600, everything else 400; size
  changes reserved for headings.

### 7.2 Spacing and density

- 4 px grid and scale unchanged.
- **new — two densities** (folds V1.x compact density): *comfortable* (V1, 32 px single-line
  rows) and *compact* (desktop only, 24 px rows, caption 12, meta column narrower). Chosen in
  Appearance; phone always comfortable (44 px targets).
- Containers keep `@container` layout; media queries only for chrome (unchanged).

### 7.3 Surfaces, borders, depth and the line-style vocabulary

- Three elevations unchanged; overlays opaque; no blur, no glass, no surface gradients.
- **Fewer separators** ("structure felt, not seen", E-27): list rows separate by spacing and a
  `line` hairline every row only in compact density.
- **new — one line-style vocabulary across the app**, extending the graph's edge tiers (ADR-0025)
  to everything that has a "final / not final" distinction:

| Style | Graph edge (V1) | Spine station (new) | Plan task (new) |
|---|---|---|---|
| solid | recorded | passed | done |
| filled in state colour | — | current | running |
| dashed | suggested by Archeus | — | proposed (plan not approved) |
| hollow | — | not reached | not started |
| dotted | unclear (when Core writes it) | — | — |

  Every style also has a word; the style is never the only carrier.

### 7.4 Motion language (proposed registry v2)

**Principle: motion is proportional to evidence.** Something moves only because Core recorded an
event the user can see the effect of; the amount of motion never exceeds the amount of news; and
silence is shown by stillness plus text, not by a loop. V1's rules (registry, idle invariant, two
clocks, transform/opacity, caps, `renderAt(t)`, no replay) all stay.

**Duration classes** (new names for V1's values; Carbon's productive/expressive split, reference study §4.9):

| Class | ms | Easing | Used by |
|---|---|---|---|
| `instant` | 0 | — | selection, focus, hover on frequent controls, everything under reduced motion |
| `quick` | 160 | `cubic-bezier(.22,.8,.18,1)` | state change, toast fade, dialog |
| `standard` | 240 | same / linear for opacity steps | pulse, arrival, camera settle |
| `layer` | 220 / 280 | same | inspector, sheet |
| `travel` | 600 | linear (constant speed) | marker, thread line |
| `orbit` | 900 | ease-in-out | presence orbit |

Rule from Material 3 (reference study §4.9): **effects (opacity, colour) never overshoot**; a spatial motion
may use a `linear()` spring with ≤ 4 % overshoot, and no registered motion currently needs one.

**Signatures — every motion has a semantic reason** (✓ = exists in V1; **new** = proposed):

| Moment | Signature | Trigger (Core) | Duration | Reduced motion | Text equivalent |
|---|---|---|---|---|---|
| **Arriving** (a row/card appears because Core created it) | none — rows appear at once (§46.2 exception kept); the T2 rule marks it | new object in a read | — | same | "changed since you looked" |
| **Thinking / planning** | **none.** Static ◌ figure + specific text | planning states | — | same | "Planning: …" |
| **Executing** | ✓ one opacity pulse per output batch (≤ 1 / 2 s / object), ✓ travelling marker on the drawn edge, ✓ halo static | `execution.*` frame | 240 / 600 | removed; static 2 px live edge | "output 4 s ago" / "live now" |
| **Quiet** (new) | none: the pulse stops; the liveness text appears with its age | Core liveness reading | — | same | "no output for 12 min" |
| **Waiting (on you)** | ✓ A-08 badge arrival once + **new** static attention band on the row | attention count rose | 240 once | band only | announce "N things need you" |
| **Requesting approval** | same as waiting; the approval card enters with ✓ A-01 | new approval | 160 | instant | assertive announce once (V1) |
| **Succeeding** | ✓ A-01 cross-fade to ✓; ✓ toast only if ≥ 10 s of work finished off screen; spine completes (no motion) | completed | 160 | instant | state word; toast text |
| **Failing** | ✓ A-01 cross-fade to ✕; **no shake, no pulse, no toast**; inline reason | failed | 160 | instant | reason text |
| **Disappearing** | none — rows leave at once (§46.2) | object left the read | — | same | — |
| **Reconnecting** | none: banner text + hollow presence node; command bar border amber (✓) | connection state | — | same | banner, announced |
| **Archeus acted** (signature) | ✓ thread line drawn once (T1), rule stays (T2) | message with `links[]` | 600 | rule appears, no travel | "Archeus updated …" |
| **System working** | ✓ orbit turns once per batch, ≤ 1 / 5 s | batch of frames | 900 | colour only | strip sentence |
| **Listening** (V2-A1) | level meter proportional to the real mic level while held | user holds push-to-talk | live, stops on release | static "Listening" | "Listening" |

**What is new is small:** a liveness reading (text), an attention band (static), and a written
rule that thinking, arriving, failing and disappearing do not move. The language is mostly a
formalisation of what V1 already does, which is the point.

**View Transitions (DEFER, V2-U6).** Same-document View Transitions could replace the
inspector/sheet keyframes 1:1. Adopt only if registered as the same motion ids, compositor-only,
and switched off under reduced motion (`::view-transition-group(*){animation:none}`).

### 7.5 Iconography and state figures

- One outline icon set, 1.5 px stroke at 20 px (DS §7, unchanged).
- **new — state figures** (the Thinking Orbs lesson, without the motion): each presentation class
  has a figure **drawn separately** at 12, 16 and 20 px (not scaled), built from the mark's own
  geometry (the cage's junction dot and orbit ring) so state glyphs, the mark and the project cage
  read as one family. Glyph characters (● ◆ ■ ‖ ◌ ✓ ✕) stay the TUI's and the fallback; the
  figures never carry meaning alone (glyph + word unchanged).
- If P21's activity record carries an **action kind** (read, search, edit, run, test), each kind
  gets a static 12 px figure beside the activity line; it changes only when the recorded action
  changes (A-01 cross-fade). This is the honest form of the orbs' "searching / composing" states.

### 7.6 Colour semantics, lighting, focus, selection, attention, execution and graph state

- **State colours:** the six V1 colours, fixed across themes (unchanged). No new hue. "Quiet" and
  "will recover" use `paused` grey with words; red stays for problems a person must resolve.
- **Lighting = activity, only:** halo, pulse, marker, cored node, orbit. No glow, bloom or ambient
  light anywhere (rulebook §27).
- **Focus:** 2 px thread ink + offset (unchanged, ADR-0028). **Selection:** `surface-2`
  background + `aria-selected` (as built). DS §9 still says selection draws a 2 px `text` left
  rule, but rulebook §41 gives a row's left edge to the thread and the built design gate fails
  anything else drawn there — a stale line for a document pass like R13-15, not a V2 decision.
- **Attention:** amber ◆ + word + **new** static row band (≤ 12 %); never more than three on Now.
- **Execution state:** the spine (P-1) + liveness text (P-3) + the V1 halo/pulse.
- **Graph state:** V1's encoding unchanged; **new** semantic zoom tiers (§8.1) and the spine as
  the largest tier's node detail.
- **The thread (ADR-0026):** extends to the spine — when Archeus moves a mission to a new station,
  the T1 line may end at that station on screen (same motion, same cap of 1).

---

## 8. Spatial UI, candidate by candidate

| Candidate | 2D sufficient? | 2.5D useful? | 3D useful? | WebGL justified? | Mobile viable? | Accessible? | Keyboard? | Reduced motion? | Low-GPU? | **Recommendation** |
|---|---|---|---|---|---|---|---|---|---|---|
| **Relations / knowledge graph** | yes | only V1's depth tiers (alpha by hop) | no (E-8) | only past ~5–10k drawn edges, measured | list < 600 px (V1) | yes, mirror | yes (V1 walk) | yes | yes (Canvas 2D, parks) | **2D, query launcher (P-6)** |
| **Mission execution (plan DAG)** | yes | no | no | no | list | yes (list is primary) | yes | n/a (static) | yes | **list by default; layered 2D DAG only when tasks have real dependencies (E-23)** |
| **Dependency / causality paths** | yes | no | no | no | text path | yes ("3 steps: A → B → C", V1 path text) | yes | camera jump | yes | **2D highlight + text (P-6), after P21 Q-B1** |
| **Resources** | n/a (forms) | no | no | no | yes | yes | yes | n/a | yes | **forms + health roll-up (P-8); a route diagram inside Why only** |
| **Attention** | n/a (queue) | no | no | no | yes | yes | yes | n/a | yes | **not spatial; a queue (P-2)** |
| **System overview** | DOM | no | no | no | strip | yes | yes | yes | yes | **strip + Now; replace the live map's canvas at low counts (§8.3)** |
| **Execution history** | 1D | no | no | no | yes | yes | yes | n/a | yes | **compact order-only timeline + spine durations (E-19)** |

### 8.1 Semantic zoom tiers for Relations (proposal)

| Rendered node size | Draws | Interaction |
|---|---|---|
| < 6 px | dot (V1 LOD), same-colour batch | hover label |
| 6–16 px | state figure (§7.5) | hover label |
| 16–40 px | figure + label (V1 labels) | click selects |
| > 40 px (focus and its neighbours) | figure + label + spine (missions) or kind + count (projects) | Enter opens |

Chosen by rendered size, so the same rule works at every zoom and window. Labels obey V1's
zoom threshold and the degraded-frame rule.

### 8.2 Scale

The V1 renderer's design matches the measured practical rule for Canvas 2D (E-9). The owed proof
is the manual 60 fps on integrated graphics at 1,000 nodes (R13 §6). V2-U5 adds: a real-corpus
measurement (E-24: tune on real graphs), aggregation above 250 nodes by project/kind clusters
(already the cluster model), and the WebGL 2D trigger (§5.2).

### 8.3 The live map

At the counts Archeus usually has (1–5 live missions), a 320 px canvas with one or two nodes
carries less than a list row. Options for V2: (a) a **flow strip** — each live mission as its
spine with the execution's liveness, one line each, DOM, zero frames when idle; (b) keep the
canvas but size it to content and show it only at ≥ N live nodes; (c) keep as is. **(a) is
recommended**: it answers "what is moving and where" at any count, works on a phone, and keeps
the full graph one click away. The rulebook's "spatial primary for overview" (Q-A2, ADR-0027) is a
user decision; changing it needs an ADR amendment.

---

## 9. Performance and accessibility constraints

Every V2 proposal against the brief's constraints. ✓ = satisfied by design; ⚠ = needs a
measurement or a rule; ✗ = fails (none proposed).

| Proposal | iGPU | 1k+ nodes | Mobile | Reduced motion | High contrast | Forced colours | Keyboard | Screen reader | Offline | Low bandwidth | CPU/GPU idle | Bundle | Memory |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P-1 spine | ✓ DOM/SVG static | n/a | ✓ | ✓ static | ✓ 2 px | ✓ CanvasText | ✓ | ✓ text equiv | ✓ | ✓ no reads | ✓ 0 frames | ~1–2 KB | ✓ |
| P-2 obligation queue | ✓ | n/a | ✓ | ✓ | ✓ | ✓ | ✓ verdict keys | ✓ groups as headings | ✓ (offline shows Decide) | ✓ | ✓ | small | ✓ |
| P-3 liveness | ✓ | n/a | ✓ | ✓ text | ✓ | ✓ | n/a | ⚠ announce changes ≤ 1/30 s | as of | ✓ ids-only frames | ✓ no timers in client | small | ✓ |
| P-4 action model | ✓ | n/a | ⚠ no keys on phone: buttons | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | ✓ | ✓ | small | ✓ |
| P-6 relations | ⚠ 60 fps owed | ⚠ measured on corpus | list < 600 px | ✓ jump | ✓ | ✓ opaque mode | ✓ V1 walk | ✓ mirror | ✗ by design (no graph offline) | ⚠ depth-bounded reads | ✓ parks | Canvas 0 KB; WebGL 2D +38 KB only on trigger | ⚠ bounded by cap 500 |
| P-7 time split | ✓ | n/a | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ table | as of | ✓ | ✓ | small | ✓ |
| §7.5 state figures | ✓ | ✓ batched | ✓ | ✓ | ✓ | ⚠ figures must render in system colours | n/a | glyph + word | ✓ | ✓ | ✓ | small | ✓ |
| §8.3 flow strip | ✓ | n/a | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ list | ✓ | ✓ | ✓ | −(canvas map removed) | ✓ |

**New gate proposed for V2-U0: a bundle budget.** V1 has none (§2.1). Proposal: the built JS and
CSS gzip sizes are recorded per release and a test fails when they grow by more than an agreed
margin without an entry in a budget file naming why. Adding any rendering or animation dependency
then becomes a visible, reviewed act. (It touches no product behaviour and could land in V1 at no
risk; it is listed under V2-U0 because it is not a V1 requirement.)

---

## 10. V2 UI opportunity matrix

| Area | V1 status | Problem | Proposed V2 direction | Technology | Value | Risk | Priority |
|---|---|---|---|---|---|---|---|
| Mission lifecycle | badge + status line | no "where is it" shape anywhere | **P-1 spine** everywhere | DOM/SVG, static | **High** | Low | **V2 Core** |
| Attention | Core order, full cards | no obligation order; heavy cards on Now; ack/snooze absent | **P-2** groups, compact-on-Now, acknowledge, snooze-until | DOM; Core records | **High** | Medium (Core ADR) | **V2 Core** |
| Liveness / execution | halo + pulse | silent ≠ visible | **P-3** liveness reading + activity line | Core reading (+P21) | **High** | Medium (Core) | **V2 Core** |
| Conversation / cards | live cards, T1 | cards don't show lifecycle; no action model | **P-4** spine on cards, Enter/Ctrl+Enter/palette, steer position | DOM | Medium-High | Low (X7 needs ADR) | **V2 Core** |
| Now | ≤ 7 blocks | fold pushed by cards and digest | P-2 compact rows + P-5 summaries + §8.3 flow strip | DOM | High | Low-Medium | **V2 Core** |
| Live map | canvas, ≤ 40 nodes | low value at typical counts | §8.3 flow strip | DOM | Medium | Medium (ADR-0027 amendment) | **V2 Core** (decision) |
| Handover | digest | no per-mission "while away" | **P-5** summaries | DOM | High | Low | **V2 Core** |
| Visual language | V1 tokens | dense lists unaligned; no density choice | meta column, compact density, line-style vocabulary, state figures | tokens + CSS | Medium | Low | **V2 Core** (foundation) |
| Motion | registry v1 | duration names ad hoc; quiet/failing rules unwritten | registry v2 classes + signature table | none new | Medium | Low | **V2 Core** (foundation) |
| Mobile | PWA, sheets | no push (P20); approvals heavy | **P-10** phone Now = Decide + summaries | DOM + P20 push | High | Medium | **V2 Core** |
| TUI | parity | Now header pre-ADR-0027; no spine | **P-12** | Python renderer | Medium | Low | **V2 Core** |
| Relations | Canvas 2D + mirror | not yet a launcher; no saved views/causality | **P-6** | Canvas 2D (WebGL 2D on trigger) | Medium-High | Medium | **V2 Later** (needs P21 data + corpus) |
| Execution time split | none | "why slow?" unanswerable | **P-7** | Core timing record | Medium | Medium (Core) | **V2 Later** |
| Resources | forms | no rolled-up health | **P-8** health + reasons | client derivation | Medium | Low | **V2 Later** |
| Work | groups | empty right side, sparse | **P-9** plan rail, density | DOM | Medium | Low | **V2 Later** |
| Offline | read-only Now | inspectors not kept | **P-11** fixed-time framing, bounded inspector cache | IndexedDB | Low-Medium | Medium (security note B7) | **V2 Later** |
| E-stop placement | strip + tray + phone | louder than its use | **P-13** decision | — | Low | Low | **V2 Later** (decision) |
| Layer transitions | CSS keyframes | — | View Transitions 1:1 | platform | Low | Low | **V2 Later** (optional) |
| 3D | V1.x-3D named | unproven value, known Qt risk | research spike with kill criteria | three.js (spike only) | Low | High | **V2 Later** (research only) |
| Thinking-orb animations, border beam, gooey, metal, image FX, avatars | — | — | — | — | — | — | **Never** |

### 10.1 V2 Core — defines the V2 experience

P-1 lifecycle spine · P-2 Attention by obligation (with Core acknowledge/snooze) · P-3 liveness ·
P-4 action model and cards · P-5 handover summaries · Now recomposed (compact Decide rows, flow
strip) · P-10 phone as handover device · P-12 TUI · the visual-language and motion-registry v2
foundation (§7).

### 10.2 V2 Later — good, but wait

P-6 Relations as query launcher (after P21's causality and a real corpus) · P-7 execution time
split (Core record) · P-8 resource health · P-9 Work plan rail · P-11 offline inspectors · P-13
e-stop placement · View Transitions · the V1.x-3D research spike · a WebGL 2D renderer (only on a
measured trigger).

### 10.3 Never / Reject

Any perpetual or ambient animation, including "thinking" or "breathing" indicators · spinner as a
substitute for evidence · Thinking Orbs, Border Beam, Gooey, Metal, Image FX, Bot Avatars ·
three.js or WebGPU in the app · a 3D or global-hairball graph as home or ornament · glass, blur,
glow, bloom, blend modes, surface gradients · an animation library dependency (Anime.js, Motion,
GSAP) · scroll-driven animation · drag-as-command, drag-to-move, swipe that performs an action ·
approvals or snoozes that time out into action · avatars, personas, greetings, personality copy ·
per-cluster hues · skins and worlds · user-composable dashboards · metric-card home · follow-the-
agent by default.

---

## 11. V1 → V2 boundary

This section exists to stop V2 research from creating V1 churn.

### 11.1 Do not touch in V1 (frozen)

- IA and the navigation table (ADR-0014); the inspector-over-destination model; tab partitions.
- The state vocabulary, glyphs, words, colours, ΔE and contrast floors; no hue accent; focus =
  thread ink.
- The motion registry, its 15 built entries, the idle invariant, two clocks, caps, no replay, the
  single parking loop; the row insert/remove exception; D-8 toasts.
- The thread (T1, T2, `│` in the TUI), mark, orbit, favicon state, operations strip.
- Pause all, Resume all and Emergency stop: semantics, confirmations, placements (strip, Work,
  tray with its native confirm, Control, chat).
- The graph: Canvas 2D renderer, layout-once, encoding, tiers, halo, marker, hull, depth, cage,
  legend, impact view, keyboard walk, mirror; the 600 / 1000 px thresholds; the live map as built.
- Relations list as the accessible authority.
- Appearance (theme, contrast, motion per client); offline snapshot scope and its read-only rule;
  pins, priority, ideas read-only, palette cache-only (D-7…D-14).
- Approval card semantics, verbs, button order, PIN step-up; every confirm with Cancel focused.
- Phone gestures: swipe reveals only; no pull-to-refresh.
- TUI: no motion, its keys and parity tables.
- Zero new runtime dependencies.

### 11.2 Small V1 corrections

**Already decided — owned by R13 §8, not by this research** (listed so V2 does not re-own them):
R13-03 one "N new messages" row; R13-04 approval-card copy (rule ids in words, local expiry, TUI
list join and hash under details, class column); R13-05 bare `why` in a thread; R13-06 `status`
in words; R13-07 chat-card wording; R13-08 one live approval card; R13-10 plan kind in words;
R13-11 no source column in the main Relations path; R13-12 "Save preferences" everywhere; R13-13
Upcoming states out of Happening now; R13-15 the three document amendments. Plus Q-A5 (Alt keys,
before P26).

**New from this research — one correction and two decision requests, all three decided by the user on 2026-10-04 as V1 corrections (rulebook §46.4 records each with its acceptance and wording constraint):**

| Id | Correction | Evidence | Risk | Value |
|---|---|---|---|---|
| **S-1** | The approval card's "What exactly will happen" table stacks into labelled rows (Task / Class / Target / Policy as key–value) when its container is narrower than the four columns need, via a container query (the codebase's existing rule, DS §5) | R13 capture `p01_now` at 390 px: headers read "Cl / as / s", "Tar / ge / t", the policy cell wraps to one word per line; the phone is the approval device (rulebook §19, the unification scenario) | **Low**: CSS only, inside one component; no copy, verb or order change; covered by the existing overflow/axe e2e at 390 px plus one assertion | **High**: the safety-critical card is unreadable on the device that most often decides it |
| **S-2** (decided: V1 correction) | The live map on Now drops the three-line graph key caption, which belongs to the full graph; keep it reachable as the canvas's accessible description and in the full graph | capture `d01_now_dark`: three lines of keys under a two-node, toolbar-less map | Low | Medium — Now's ≤ 7-block budget; **but** discoverability of keyboard use is an a11y concern, hence a decision |
| **S-3** (decided: V1 correction) | The TUI's Now header uses ADR-0027's state sentence ("Archeus is working on 2 missions. 1 needs you.") instead of the pre-ADR line | `screens.py` Now header (code survey) vs DS §11 "State sentence" | Low (copy, parity fixture) | Medium — one vocabulary across clients (DS §1.6); whether ADR-0027 §5 binds the TUI is not recorded, so it is the user's call |

Nothing else in V1 is recommended for change.

### 11.3 Move to V2

The lifecycle spine (P-1) · Attention by obligation with acknowledge and snooze (P-2) · liveness
(P-3) · the action model and spine on cards (P-4) · handover summaries (P-5) · Relations as a
query launcher with saved views, semantic zoom tiers and causality overlays (P-6) · execution time
split (P-7) · resource health (P-8) · Work plan rail and compact density (P-9) · the phone as the
handover device (P-10) · offline as a fixed-time view with bounded inspectors (P-11) · TUI spine
and verdict keys (P-12) · e-stop placement (P-13) · the live map's replacement by a flow strip
(§8.3) · the visual-language and motion-registry v2 foundation (§7).

### 11.4 Do not build

Everything in §10.3.

---

## 12. Proposed V2 UI roadmap

Sequenced by **dependency and by what each phase makes measurable**, not by visual ambition. Every
production phase starts after P26 (as V2-A does), each ends at a gate with BEFORE/AFTER captures
on a real Core (ADR-0029), mutation-verified gates, and the user's sign-off.

| Phase | Content | Depends on | Core work | Exit evidence |
|---|---|---|---|---|
| **V2-U0 Evidence** (research; may run any time, no product code) | the owed V1 measurements (60 fps at 1,000 nodes on an iGPU; real-phone offline cold start; Qt shell manual checks); a screen-reader pass with live work; a **real-corpus** graph set from the user's projects (E-24); a usage diary of what the user actually opens; the bundle budget gate (§9) | — | none | a dated report under `docs/research/`; budget gate green |
| **V2-U1 Foundation** | tokens v2 (meta column, compact density, line-style vocabulary, attention band); motion registry v2 (duration classes, signature table, written "does not move" rules); state figures at 12/16/20 px; the **spine primitive** (SPA + TUI ASCII) with its text equivalent | V2-U0, P26 | none | spine renders every Core mission state (generated from `states.py`, like presentation classes); ΔE/contrast gates extended; idle invariant unchanged |
| **V2-U2 Interaction** | P-2 obligation groups (client), compact Decide rows on Now; P-4 action model + spine on cards; P-5 handover summaries; P-12 TUI verdict keys; §8.3 flow strip (if the user amends ADR-0027) | V2-U1 | **acknowledge + snooze-until records** (new ADR) | every Attention item reachable and decidable by key in SPA and TUI; Now above the fold at 1440 × 900 with 3 needs-you items and 5 live missions |
| **V2-U3 Living state** | P-3 liveness reading + activity line; P-7 execution time split | V2-U2, **P21** (`live_work`, A-17 record) | **liveness rule + per-execution timing record** (new ADR) | a stalled fake harness reads "quiet" then "unresponsive" with no client timer; zero frames while quiet |
| **V2-U4 Mobile** | P-10 phone Now; short-lived phone approvals; P-11 offline fixed-time view | V2-U2, **P20** push and credential review | per P20 | physical-phone acceptance (not emulation) |
| **V2-U5 Relations** | P-6 saved views, semantic zoom tiers, origin and causality overlays, minimap threshold; renderer decision by measurement (Canvas 2D kept, WebGL 2D only on trigger) | V2-U1, **P21** causality (Q-B1), V2-U0 corpus | none beyond P21 | 60 fps on iGPU at the corpus's largest view; mirror parity; Honeycomb test: the view is used to answer a question, recorded in the usage diary |
| **V2-U6 Polish (optional)** | P-8 resource health, P-9 plan rail, P-13 e-stop placement, View Transitions 1:1, the V1.x-3D research spike under its kill criteria | any | none | each item independently; the spike reports even if it fails |

Why this order: the spine and the obligation model change what every surface shows, so they come
first; liveness and Relations depend on data that P21 creates, so they come after it; the phone
depends on P20 push; polish waits for evidence that it matters.

---

## 13. Recommended next architecture and design documents

All PROPOSED; numbers are assigned when written (the last ADR is ADR-0052).

| Document | Decides | Needed by |
|---|---|---|
| **ADR — V2 interaction model: the handover model** | §6.1–§6.2 (IR-1…IR-8) as the V2 rulebook's root | V2-U1 |
| **ADR — Mission lifecycle spine** | stations, state mapping (generated from `states.py`), sizes, text equivalent, TUI form | V2-U1 |
| **ADR — Attention obligations, acknowledge and snooze** | groups; acknowledge ≠ resolve; snooze conditions; never times out into action (IR-5); the Core records and events | V2-U2 |
| **ADR — Liveness and the execution timing record** | Core-derived active / quiet / unresponsive; thresholds per harness; the time-split record; no client timers | V2-U3 |
| **ADR — UI dependency policy** | no animation/3D library in the app; the bundle budget gate; the WebGL 2D trigger (§5.2); the site is out of scope | V2-U0 |
| **Amendment — ADR-0016 / ADR-0030: V1.x-3D re-scoped** to a research spike with a hypothesis and kill criteria | §5.2 | before any V1.x-3D work |
| **Amendment — ADR-0027: overview form** (live map → flow strip), if the user agrees | §8.3 | V2-U2 |
| **Amendment — ADR-0024: motion registry v2** (duration classes; written no-motion moments; liveness has no motion) | §7.4 | V2-U1 |
| **Design doc — `ARCHEUS_V2_VISUAL_LANGUAGE.md`** | §7 as a rulebook with tokens, figures and the signature table; supersedes nothing in V1 | V2-U1 |
| **Design doc — V2 surface specifications and wireframes** | Now, Attention, mission inspector header, phone Now, TUI Now — wireframes before code (the V1 prompt's own rule) | V2-U1/U2 |
| **Prototypes (throwaway, outside the product)** | spine at three sizes; obligation queue; flow strip; semantic zoom tiers on the real corpus — each judged by the user on captures | V2-U1/U2/U5 |
| **testing-strategy — V2 section** | spine-coverage gate (every state maps), obligation-order gate, liveness-without-timers gate, bundle budget, the V2 template test | V2-U1 |
| **Document pass — DS §9 selection wording** (§7.6) | align DS §9 with rulebook §41 and the built gate | any time (documents only) |

---

## 14. Method, evidence and gaps

- **V1 first-hand:** the rulebook, design system, R13 (including its correction pass and the
  user's §8 decisions), ADR-0014/0015/0016 and the visual ADR titles, the plan's P20–P26 and §31,
  the V2 assistant-layer document, the 2026-10 external research; a full read-only survey of
  `clients/app/src`, `tokens/*`, `tools/gen_ui.py`, `archeus/cli/tui/`, the Qt shell and the UI
  tests (file:line in the survey); the R13 captures viewed directly (`d01_now_dark`,
  `d02_missionA_now`, `d04_missionB_plan_edit`, `d05_missionA_relations`, `d06_attention`,
  `d07_work`, `x01_insp_viewport`, `p01_now`).
- **External:** the reference study's four passes (E-1…E-37).
- **Not done:** no new captures on a real Core; no measurement on Archeus hardware; no user
  testing. Every "High value" in §10 is a design judgement to be confirmed by V2-U0's usage diary
  and the prototypes, not a measured result.
- **Conflicts surfaced, not resolved:** DS §9's selection wording vs rulebook §41 (stale text);
  "spatial primary for overview" (ADR-0027) vs §8.3's flow strip; the TUI Now
  header vs ADR-0027 §5 (S-3, since decided: rulebook §46.4).
- **Git state:** committed with the visual direction and the V2 UI architecture in one documentation commit (2026-10-04). Nothing pushed;
  `.agents/` and `.codex/` untouched.
