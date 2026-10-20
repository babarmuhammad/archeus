# LE-5: the motion middle — press, reveal, expand, collapse, reorder, count, release, navigation, approval, phone push (2026-10-05)

**Result: PASS for the lean set (press, hover, reveal, disclose/collapse, confirm/refuse, push/pop,
peer crossfade, reorder without a spring); DEFER count, tooltip group and release; grid-row
disclosure STOP (again).** In the real Qt shell every primitive held p95 16.7–16.8 ms with max
16.8 ms (one vsync on a 60 Hz panel) on Intel UHD, and the page parked — 0 rAF callbacks, 0
running animations — after every job. In headed Chromium with real input every interaction
reached the next paint within one frame, including clicks that landed mid-animation. Every
animation the bench created was `transform` or `opacity`. **No animation library is needed**:
the platform covered every primitive, and reveal needs no JavaScript at all. The feel is a human
gate (H-8).

Lab: `lab/motion.html` with `lab/middle.js` + `lab/middle.css` (each primitive fenced). Drivers:
the V2-U0 tools unchanged (`v2-u0/tools/measure_qt.py`, `measure_browser.py`) via
`tools/motion_measure.py`, plus an Event Timing input pass. Results: `results/le5/qt.json`,
`qt-reveal.json`, `browser.json`, `input.json`; filmstrips `results/le5/film/strip_*.png` (0, 25,
50, 75, 100 % of each primitive's own duration, seeked, plus its reduced form at rest).

## 1. The primitives as built

All follow LR Appendix 2's registry; frequency decides amplitude (rulebook §36).

| Primitive | Form | Reduced | Notes |
|---|---|---|---|
| press | `:active` scale .97, 100 in / 160 out (CSS) | tint only | |
| hover | colour 120 ms, opt-in per control (CSS) | instant | No hover wash on every row in Qt (rulebook §34) |
| **reveal** | Popover + anchor positioning + `@starting-style`: fade + scale .96 → 1 + 4 px from the trigger, 160 in / 120 out — **CSS only** | opacity only | **Answers LQ-4: works in QtWebEngine 6.11** (`popover`, `anchor-name`, `@starting-style`, `linear()` all supported in the Qt run) |
| summon | palette at 0 ms | same | no code |
| disclose / collapse | body in place; siblings by FLIP 240 / 200 ms; content fades with 4 px; collapse fades a clone so nothing jumps | instant + 120 ms fade, focus kept | One spatial primitive per region (`M.claim`) |
| reorder | FLIP to the new group, 240 ms, **no stagger**, ≤ 1 per 500 ms, > 30 movers = re-render | instant | The settle `linear()` spring is optional (§3) |
| count | one glyph height, 160 ms, tabular figures; `aria-label` carries the value | instant | |
| release | 1:1 drag, rubber-band past the bounds, snap to the point **projected** from velocity, by an analytic spring (ζ 0.86) **sampled into WAAPI keyframes** — no rAF loop | 160 ms ease-out | Shows a gesture release does not need the rAF loop LR §11 assumed |
| peer navigation | 120 ms opacity by pointer; **instant by keyboard** | instant | Never a directional slide |
| confirm | label becomes "Approved 14:02", the row recedes **in place**, focus moves to the next decision at once | text only | The row does not leave and pull rows under the pointer |
| refuse | the reason beside the item, focus to the recovery control; no shake | text only | |
| push / pop | hierarchical page from the right, 280 / 240 ms; owns a history entry | instant | Only depth slides; peers never do |
| tooltip group | first 700 ms, peers instant within 300 ms; focus shows it too | opacity only | |
| interruption | any `pointerdown`/`keydown` (capture phase) finishes every running middle animation first (F-5) | — | |

## 2. Measured

### 2.1 Real Qt shell (QtWebEngine 6.11, Chromium 140, ANGLE D3D11, Intel UHD, 1,440 × 900 and 390 × 844)

| Job | p95 (ms) | max (ms) | LoAF | Idle after every event | Idle after job (rAF / anims) |
|---|---:|---:|---:|---|---|
| press | 16.8 | 16.8 | 0 | ✓ | 0 / 0 |
| reveal (re-run; the first run measured a hidden page) | 16.8 | 16.8 | 0 | ✓ | 0 / 0 |
| tooltip | 16.7 | 16.8 | **1 (592 ms)** | ✓ | 0 / 0 |
| count | 16.7 | 16.8 | 0 | ✓ | 0 / 0 |
| disclose | 16.7 | 16.8 | 0 | ✓ | 0 / 0 |
| collapse | 16.8 | 16.8 | 0 | ✓ | 0 / 0 |
| disclose by grid-rows (rejected form) | 16.7 | 16.8 | 0 | ✓ | 0 / 0 |
| reorder | 16.7 | 16.8 | 0 | ✓ | 0 / 0 |
| confirm | 16.7 | 16.8 | 0 | ✓ | 0 / 0 |
| refuse | 16.8 | 16.8 | 0 | ✓ | 0 / 0 |
| peer navigation | 16.7 | 16.7 | 0 | ✓ | 0 / 0 |
| push / pop | 16.7 | 16.8 | 0 | ✓ | 0 / 0 |
| release | 16.8 | 16.8 | 0 | ✓ | 0 / 0 |
| interrupt (click mid-disclosure) | 16.7 | 16.8 | 0 | ✓ | 0 / 0 |
| reduced: disclose, reorder, count, push, release, confirm, reveal | 16.7–16.8 | ≤ 16.8 | 0 | ✓ | 0 / 0 |
| phone 390 × 844: push, release, disclose | 16.7–16.8 | 16.8 | 0 | ✓ | 0 / 0 |

16.7 vs 16.8 is the vsync quantisation the PR-1…PR-6 records also show; the ">16.7" counts in the
raw JSON are those 16.8 ms frames, not dropped frames (max never exceeds 16.8). The one 592 ms
long-animation-frame entry in the tooltip job is **not** reflected in any rAF interval (max
16.8) and did not recur; its cause is not identified. Tooltip is deferred regardless (§3).

**Interruption:** in all 8 Qt repetitions, 10 animations were running when the input arrived and
all 10 had reached their end state before the input's own handler ran (0.1–0.2 ms).

### 2.2 Input → next paint (headed Chromium, real CDP input, Event Timing API)

Event Timing reports only interactions ≥ 16 ms, so "< 16" means every one was faster.

| Interaction | n | ≥ 16 ms | Worst |
|---|---:|---:|---:|
| disclose toggle (click) | 20 | 3 | **16 ms** (one frame) |
| press (click) | 20 | 0 | < 16 |
| menu open / close (click, Escape) | 20 | 0 | < 16 |
| tab switch (click) | 20 | 0 | < 16 |
| approve (click; focus advances) | 12 | 0 | < 16 |
| **click landing mid-disclosure** | 12 | 0 | < 16 |
| the same six with reduced motion | 104 | 0 | < 16 |

**Keystroke safety:** pressing Enter immediately after Approve approved the **next** decision
(row 1 and row 2 "Approved 14:02", row 3 untouched) — focus had advanced and the keystroke was
not lost (rulebook §17).

### 2.3 CPU (headed Chromium, per repetition, a loaded machine)

| | Task | Layout | Style |
|---|---:|---:|---:|
| disclose by **FLIP** | 31 ms | **1.2 ms** | 5.9 |
| disclose by **grid-rows** | 51 ms | **7.0 ms** | 2.5 |
| reveal (top layer + anchor) | 62 ms | 18.0 | 18.4 |
| everything else | 11–34 ms | 0.4–1.6 | 0.3–5.2 |

Grid-row interpolation costs **≈ 6× the layout** of FLIP for the same disclosure: it animates
layout every frame. In Qt it still held 60 fps on this page, which is exactly why it must stay a
rule rather than a judgement call — it is cheap until the list is long. Reveal's style/layout
cost is the top-layer and anchor resolution on open; it is once per open, not per frame.

Browser frame timings for four jobs (tooltip, reorder, nav, release at desktop size) show 1,004 ms
gaps: Windows occlusion throttling of the headed window, not the primitive. **Qt is the frame
authority here** (its driver holds the window topmost), and the Qt figures above are clean.

### 2.4 The property audit

Every keyframe the bench created: `transform` 84, `opacity` 12; CSS transitions: `transform`,
`opacity`, and the discrete `display`/`overlay` pair that a popover's exit needs (no paint), plus
`background-color` on the opt-in hover control (120 ms, one control) and `grid-template-rows` in
the rejected form only. Nothing else.

### 2.5 Accessibility forms

Reduced motion: every primitive resolved to an instant change or a ≤ 160 ms opacity change, with
focus kept, and the Qt jobs ran 0 transform travel. Quiet: count is instant. Forced colours: the
decided row stays at full opacity (its label carries the state). High contrast and reduced
transparency: nothing in the bench is translucent.

## 3. Recommendation

| Primitive | Verdict | Why |
|---|---|---|
| press, hover, reveal, summon | **Ship (lean set)** | Near-free (≤ 0.22 KB), CSS-only, one frame |
| disclose / collapse, confirm / refuse, push / pop, peer nav | **Ship (lean set)** | They carry the "several a day" spatial meaning: origin, continuity, the decision becoming a result, depth on the phone |
| reorder | **Ship without the spring** | 0.11 KB with the standard ease; the `linear()` settle adds 0.32 KB for a difference nobody has been asked to see |
| count | **Defer** | A number changed by an event already gets a ≤ 160 ms step (A §F); 0.32 KB for a roll |
| tooltip group | **Defer** | 0.40 KB; this app's proof-of-life tooltips are few; the native delay is acceptable until a human says otherwise; the one unexplained long frame was in this job |
| release (+ spring) | **Defer until H-3** | 0.84 KB; the chevron/tap path is required anyway (rulebook §28); add drag only if the thumb test asks for it |
| grid-rows disclosure | **Stop** | Layout animation (LR §15, rulebook §53) |
| any animation library | **Reject** | Not needed for any primitive (LR R-9 confirmed) |

**Bytes:** lean set ≈ **1.49 KB** marginal (`le6`); the full set 2.80 KB.

## 4. Open

- **H-8** a day of use of the lean set in the Qt shell.
- LQ-5 (does Windows' Animation effects setting reach `prefers-reduced-motion` in Qt?) was not
  tested — it needs the OS setting flipped, which this session did not do on a shared machine.
