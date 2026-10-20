# LE-6 (LD-1): the budget — which additional bytes materially improve the product? (2026-10-05)

**Result: do not raise the V2 budget to 16–18 KB. The evidence supports ≈ 12.5 KB of V2 visual
behaviour, and moving the information layer (language, context, composition — ≈ 3 KB) out of the
visual-behaviour budget into the ordinary V1 bundle gate, where product UI already lives.** That
split is a decision for the user (LD-1), not a measurement. Measured: `tools/budget.py` →
`results/le6/budget.json`.

## 1. Method — and why the committed figure is lower than recorded

V2-U0 priced each part as `gzip -9` of the part **alone**, crudely de-commented. That is not what
a user downloads. This phase prices every part two ways:

- **isolated** — the V2-U0 method, for comparison;
- **marginal** — `gzip(V1 bundle + part minified by the SPA's own minifiers) − gzip(V1 bundle)`,
  using Vite 8's own rolldown/oxc (JS) and lightningcss (CSS) from `clients/app/node_modules`.
  Every declared function is kept live so the minifier cannot delete an unused renderer, and the
  cost of that keep-alive statement is subtracted (`price()` in `budget.py`). Without that guard
  the language layer priced at 4 bytes — the minifier had deleted it.

**Baseline today:** the V1 bundle as built in the working tree is **146.6 KB gzip JS** (481.0 KB
raw) and **5.96 KB gzip CSS** — 0.9 KB of JS above A §Q's 2026-10-04 baseline, all of it V1 work,
none of it V2.

**The V2-U0 commitment, re-priced where the code is fenced:**

| Part | Recorded (V2-U0) | Marginal, real minifier |
|---|---:|---:|
| PR-5 figures + spine | 3.45 KB | **3.04 KB** |
| PR-6 governor (as built, with diagnostic strings) | 1.47 KB | **1.20 KB** |
| PR-6 K-1…K-3 base | 2.13 KB | **1.70 KB** |
| PR-4 display type | 0.24 KB | **0.21 KB** |
| PR-2 spatial morph, PR-3 recede | 2.2 + 1.1 KB | not re-priced (inline in the lab HTML, not fenced) |

The four re-priceable parts come in **12–20 % below** their recorded figures. Applying the
measured governor ratio to the lean (no-strings) governor and keeping PR-2/PR-3 at their
recorded values, **the real V2-U0 commitment is ≈ 9.2 KB, not 9.7** (≈ 8.7 KB if PR-2/PR-3 shrink
the same way, which is plausible and unmeasured). The headroom under 10 KB is ≈ 0.8–1.3 KB, not
0.3.

## 2. What each later-V2 capability costs (marginal, bytes gzip)

| Capability | Marginal | Kind | Evidence that it improves the product |
|---|---:|---|---|
| press (`:active` scale .97) | 52 | CSS | Response craft; 0 latency cost (`le5`) |
| hover (colour, opt-in per control) | 31 | CSS | Affordance |
| reveal (Popover + anchor + `@starting-style`, no JS) | 217 | CSS | Origin of menus; **works in Qt 6.11** (`le5`) |
| summon (palette at 0 ms) | 0 | behaviour | — |
| peer navigation crossfade | 78 | JS | Minor |
| motion core (tracked WAAPI, one-per-region, settle on input) | 358 | JS | Required by every JS primitive; overlaps PR-2's engine |
| flip (shared) | 214 | JS | Needed by disclose and reorder |
| disclose / collapse | 392 | JS + CSS | Rows that expand in place without a jump (several a day) |
| confirm / refuse | 243 | JS + CSS | The approve → "Approved 14:02" moment and focus advance (rulebook §17) |
| push / pop (phone page, history-owned) | 242 | JS + CSS | LD-5's full-page decision, Back never exits (`le4`) |
| reorder | 110 | JS | Group changes move instead of jumping |
| spring (analytic + `linear()` settle) | 318 | JS | Only reorder's settle curve and release need it |
| count (digit roll) | 320 | JS + CSS | Weak: a number changed by an event; the governor already allows a ≤ 160 ms step |
| tooltip group (700 → 0 ms) | 395 | JS + CSS | Weak in this app: proof-of-life tooltips are few |
| release (drag + projected spring) | 520 | JS | Only if the phone strip is draggable; the chevron tap is the required path anyway (rulebook §28) |
| e-stop two-step (LD-7) | 320 | JS + CSS | Safety: no modal, no single-tap kill (`le4`) |
| human-language layer | 511 | JS (strings) | The single largest legibility gain (`ld9`): 0 machine strings at depth 1–2 |
| mission context with provenance | 1,426 | JS + CSS | Q1/Q2 answered on the row (`le1`); most of the bytes are the provenance explanations, which could move to a lookup |
| desktop composition C (panes) | 142 | CSS, gross | Evidence one click away at 1,700 (`le1`) |
| phone composition (tabs, strip, decision bar) | 442 | CSS, gross | Phone Now 1.4 screens instead of 5.1 (`le1`) |
| day's light R1 lanes | 1,650 | JS + CSS | Best picture, names no mission (`le3`) |
| day's light R2 ledger | 959 | JS + CSS | Answers everything, no shape |
| **day's light R3 ledger + traces** | **1,572** | JS + CSS | Answers everything with a shape (`le3`) |
| *(rejected)* disclose by grid-rows | 46 | CSS | Cheap and wrong: animates layout (`le5`) |

Priced as they would ship together (one dictionary):

| Bundle | Marginal |
|---|---:|
| **Information layer**: language + context + e-stop + press/hover/reveal | 2.42 KB |
| Composition CSS (phone + desktop), gross — it *replaces* V1's `.now-grid` and phone rules, so net ≈ 0 | 0.57 KB |
| Motion middle, **lean** (core, flip, disclose, confirm, push; CSS press/hover/reveal) | **1.49 KB** |
| Motion middle, full (+ spring, reorder, count, release, tooltip, nav) | 2.80 KB |
| Day's light R3 | 1.57 KB |

## 3. What is almost free, and what genuinely costs

**Almost free (≤ 0.6 KB each, or net zero):** the three-place IA and both compositions (CSS that
replaces CSS), press, hover, reveal (CSS only, thanks to Popover + anchor positioning +
`@starting-style` in Chromium 140 — no JS at all), summon, the language layer (0.51 KB of strings
that replace V1's strings), the e-stop two-step. **These are where the brief's product goals are
won** — `le1`'s question proxy and `le4`'s phone heights come almost entirely from them.

**Genuinely costs:** the context renderer (1.4 KB, reducible), the JS motion primitives (1.5 KB
lean / 2.8 KB full), and the day's light (1.6 KB).

**Bytes the evidence does not justify yet:** count, tooltip group, release (and the spring it
needs), R1 lanes *in addition to* R3. Together ≈ 1.6 KB + 1.65 KB.

## 4. Recommendation for LD-1

| Option | Total V2 visual behaviour | What ships | Verdict |
|---|---:|---|---|
| (a) keep 10 KB | ≈ 9.2 committed + 0.8 | CSS-only middle; no day's light; no JS disclose/confirm/push | Loses the noun and the phone page transition — the two things LD-4 and LD-5 exist for |
| **(b) ≈ 12.5 KB visual behaviour; information layer under the V1 bundle gate** | ≈ 9.2 + 1.5 (lean middle) + 1.6 (R3) ≈ **12.3** | Everything in §3 "almost free" + lean middle + R3; count/tooltip/release deferred until a human test asks for them | **Recommended** |
| (c) ≈ 16–18 KB (research proposal) | ≈ 9.2 + 2.8 + 1.6 + 1.7 (R1) + 2.4 (info layer counted as visual) ≈ 17.7 | Everything | Not justified: the extra ≈ 5 KB buys count, tooltips, release, a second day's light and accounting, none of which moved a measure in this phase |

**Why (b) is not an accounting trick:** A §Q's 10 KB is a budget for *visual behaviour* —
motion, light, depth, figures. The language layer, the context block and the compositions are
product UI that replace existing V1 markup and strings; they belong under the bundle gate that
already governs V1's 146.6 KB, with a per-change size record. If the user prefers one number,
(b) is ≈ 15 KB all-in, still below (c), and every item keeps pricing itself first.
