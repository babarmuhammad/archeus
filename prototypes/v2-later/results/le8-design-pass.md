# LE-8: the design pass, against Apple's Human Interface Guidelines and the installed design skills (2026-10-05)

**Result: PASS — presentation only, with three small regressions.** Clicks and words are unchanged
on every question, and every accessibility, honesty and safety gate holds. The phone answers
four of five scrolled questions sooner. The costs: the small phone scrolls 6–14 px further, and
the phone decision page and Missions page are ≈ 60 px taller, from the two-row decision bar and
the list-header spacing (§4).
The pass costs **1.30 KB marginal** (gross: it restyles rules production would replace rather
than add to). No word, order, route, data field or `data-q` answer changed, nothing moves, and
the V2-U0 identity rules hold. **Every change below is a proposal (status: *Proposed (design
pass)*) and none is decided.** The gates are H-1, H-2 and H-3, which now run on the polished lab.

Lab: `lab/polish.css` (linked by `ia.html` and `light.html`), the `typeset` fence in `ia.js`, the
axis in `light.js`'s `hybrid` fence. **`?dp=0` renders the pre-pass lab**, so every comparison is
like for like. **Variant A (the V1 replica) never gets the pass**, because it is the baseline.
Captures: `results/le8/dp_phone.png`, `dp_desk.png`, `dp_desk_c.png` (before/after at true
relative height); `results/le8/before/` keeps the pre-pass captures. Diff: `tools/dp_diff.py` →
`results/le8/dp_diff.json`.

## 1. Sources, and how far each was followed

| Source | Used for | Not taken, and why |
|---|---|---|
| **Apple HIG** (layout, typography, lists and tables, tab bars, buttons, accessibility) | One leading edge per list; separators that start at the text; section headers as list headers; tabular digits; the selected tab as a filled shape; the primary action as the full-width thumb target; a mini-player-style strip one layer up; optical sizes and tighter tracking at display sizes; text that never orphans a number from its unit | **Liquid Glass, translucency and blur** (V2-U0 PR-3: depth without blur; the Qt readback lesson). **SF Symbols tab icons** (no glyph set yet, and a figure-styled glyph would blur PR-5's "figures mean state"). **Large-title collapse on scroll** (motion with no event) |
| `design-audit` (bencium) | The 15-dimension audit (§2) and its reduction filter | Its "wait for approval before implementing" step is met by this being lab-only and gated on LD/H decisions |
| `frontend-design` (claude-plugins-official) | The tells list: middle-dot meta strings, monospace for small data, a `→`/`⌃` glyph on controls | Its "take aesthetic risk" brief is deliberately not followed: V2-U0's identity (restraint, the thread) wins, as the skill itself says a brief must |
| `web-design-guidelines` (Vercel, fetched fresh) | Hover/pressed states, `touch-action`, tap highlight, `theme-color`, `text-wrap`, tabular nums, `…`, non-breaking spaces, sticky chrome not covering focus | Skip link (owed: §5) |
| `typography` (bencium) | Non-breaking spaces between figures and units; separators bound to the preceding word; one tier quieter for punctuation | — |
| `bencium-controlled-ux-designer` / `-impact-designer` | Their shared warning: *do not copy Apple's look* (no glass, no mimicry) | That warning is why the pass takes Apple's **principles** (clarity, deference, hierarchy) and none of its surfaces |

## 2. The audit (before)

Captured from `results/le8/before/` at 1,440 × 900 and 390 × 844, dark, light and high contrast.

| # | Dimension | Finding |
|---|---|---|
| F-1 | Alignment | Titles in Needs you start at x = 290 and in Running/Stopped at x = 282: the 2 px rail plus its padding pushed the decide group 8 px right of every other list |
| F-2 | Typography | Orphans: "expires in 8 / min" (desktop row), "2 running · 2 / stopped" (phone verdict), "step 4 of / 7" |
| F-3 | Typography | Elapsed time ("20 min") set in Cascadia Mono, the only monospace on the row; a duration is a figure, not code |
| F-4 | Hierarchy | Section headers ("Needs you", "Running") set at title size in the primary colour, competing with the verdict two steps above them |
| F-5 | Hierarchy | Meta strings use " · " as a separator at full secondary weight; the dots read as content |
| F-6 | Components | The phone tab bar's selected marker is a 2 px line across one third of the bar's top edge, which reads as a progress bar |
| F-7 | Components | "Ask for changes" wraps to two lines in the 103 px phone decision bar; Approve is only 33 px wider than Reject |
| F-8 | Components | No hover or pressed state on any button; no `touch-action`; default tap highlight |
| F-9 | Hierarchy (phone) | Two bordered buttons in a 52 px header (compose and Stop all) carry equal weight; the e-stop should be the one framed control |
| F-10 | Depth | The strip is a flat surface-2 box: content shows through the 8 px gaps around it and between it and the tabs |
| F-11 | Iconography | The strip's `⌃` says "expand upward"; the strip pushes a page, which is `›` |
| F-12 | Desktop header | The compose control reads as a button, not as the field it opens; `Ctrl K` set in monospace |
| F-13 | Day's light | Hour labels laid out by `space-between`, so 12 and 18 sit 2–5 px off their ticks; every mission title underlined like prose |
| F-14 | Theming | No `theme-color` (the PWA status bar in H-3 would be the browser default) |
| F-15 | Accessibility | No skip link past the header and the places on the desktop (not fixed: §5) |

## 3. The changes (DP-n)

All in `polish.css` unless marked. Tokens are V1's; the only new values are three `color-mix()`
tints of V1's own `--text` over `--bg` and one shadow.

| DP | Change | Fixes | HIG / skill rule |
|---|---|---|---|
| DP-1 | Display tracking −1.2 %; `text-wrap: balance` on headings, `pretty` on rows and prose; **typeset pass** (`ia.js`, text nodes only): non-breaking space between a figure and its word, the separator bound to the word before it and drawn in `--text-3` | F-2, F-5 | HIG typography (tracking by size); typography skill |
| DP-2 | Section headers become list headers: body size, 600, `--text-2`, 28 px above and 6 px below (proximity groups the header with its list); content headings on decision and mission pages keep `--text` | F-4 | HIG lists: section header |
| DP-3 | One leading edge: fixed 36 px figure column, the decide rail drawn as an inset shadow inside the padding, separators that start where the text starts, none under the last row | F-1 | HIG lists: inset separators; design-audit: alignment |
| DP-4 | Durations in the text face with tabular digits, `--text-2` | F-3 | HIG: tabular figures in columns; frontend-design: no mono for small data |
| DP-5 | Instant hover and pressed states (no transition, so nothing animates); the e-stop excluded so "armed" can never be hidden under a hover | F-8 | web-design-guidelines; A §F press |
| DP-6 | Header: compose as a plain glyph on the phone, as a field with a keycap on the desktop; Stop all is the only framed control; current place in the sidebar as a filled shape at 600 | F-9, F-12 | HIG toolbars: one prominent control |
| DP-7 | Phone tab bar: selected place as a filled capsule; 48 px targets in a 60 px bar | F-6 | HIG tab bars |
| DP-8 | Phone strip one layer up: 14 px radius, top highlight and a shadow (PR-3: tone and shadow, no blur), on an opaque band shared with the tabs so nothing shows through; chevron `›` (`ia.js`) | F-10, F-11 | HIG: mini player; PR-3 |
| DP-9 | Phone decision bar: Reject and Ask for changes share one row, **Approve is the full-width 52 px target** at the bottom edge, in DOM order | F-7 | HIG: primary action in the thumb zone |
| DP-10 | Day's light: hour labels placed by the traces' own `x()` (`light.js`); mission titles plain until hover | F-13 | design-audit: alignment |
| — | `theme-color` for dark and light (`ia.html`) | F-14 | web-design-guidelines |

## 4. What the measures say (before → after)

Full re-runs of `ia_probe.py`, `light_probe.py` and `mutate_gates.py` on the polished lab, diffed
against the last pre-pass results (`results/le1/probe_pre_dp.json`, `results/le3/probe_pre_dp.json`).

| Measure | Before | After | Note |
|---|---|---|---|
| Steps (clicks) and words read, all 8 questions × every variant and device | — | **unchanged** (0 of 216 cells) | The pass changes no word and no route |
| Scroll to an answer, phone 390 | Q4 290 · Q5 9 · Q6 658 · Q7 132 · Q8 62 | **272 · 0 · 640 · 116** · 68 | Q5 now fully on the first screen; Q8 +6 px |
| Scroll to an answer, small phone 360 | Q4 412 · Q5 131 · Q6 816 · Q7 254 · Q8 273 | 424 · 140 · 828 · 268 · 279 | **+6 to +14 px worse**: the bottom chrome is 4 px taller and `text-wrap: pretty` moves a word down on the narrowest rows |
| Scroll, desktop | Q6 172 (B) · 204 (C) | 174 · 206 | +2 px (28 px header spacing) |
| Phone Now height | 1,228 px (1.45 screens) | **1,206 (1.43)** | The verdict fits one line |
| Phone decision page | 1,501 px (1.78) | 1,561 (1.85) | The taller two-row decision bar (+60 px) |
| Phone Missions | 1,422 px (1.68) | 1,481 (1.75) | Five list headers at 28 px above instead of 20 |
| Desktop screens (every route, B and C) | — | ±5 px | — |
| Phone decision bar | Reject 58 × 103 · Ask 58 × 103 · Approve 58 × 136 | Reject 48 × 175 · Ask 48 × 175 · **Approve 52 × 358**, at the edge | "Ask for changes" on one line; Approve 2.6× wider |
| axe WCAG 2.2 AA, B and C (36 runs) | 0 | **0** | A (the replica): 1 per run, its unlabelled field, as before |
| Computed text contrast below floor, B and C | 2 (the strip chevron, phone light) | **0** | See note 1 |
| Targets under 44 px (phone) / 24 px (desktop) | — | **unchanged** on every screen | — |
| Machine strings at depth 1–2 · duplicate decisions · e-stop visible · horizontal scroll | 0 · 0 · 6/6 · none | **0 · 0 · 6/6 · none** | — |
| 200 % text: horizontal scroll / clipped verbs | none / 0 | **none / 0** | The decision bar stacks to one column |
| Phone flows: Back stays in the app; e-stop arms, lapses after 3 s, engages; dialogs | ✓ ✓ ✓ ✓ 0 | **✓ ✓ ✓ ✓ 0** | The e-stop is excluded from the hover state (DP-5) |
| Day's light: 56 renders, unsourced marks / axe / idle | 0 / 0 / 0 | **0 / 0 / 0** | 59 → 67 drawn elements in R3: the axis now carries its own `data-src` |
| Lab gates (`mutate_gates.py`) | 6/6 killed | **6/6 killed** | See note 2 |
| Bundle | — | **1.30 KB marginal** (pass) · R3 1.61 → **1.72 KB** (the aligned axis, +0.11) | Gross: `le6` method; see §6 |

Notes:

1. **The pre-pass full run still carried the chevron defect**, because after its fix only the
   question walks had been re-run (`ia_probe.py questions`). This is the first full run that
   confirms 0. Phase record §10's "now 0" was right about the code and is now measured.
2. **The pass's first full run failed the contrast gate, and both causes were real issues:**
   (a) the separator, drawn in `--text-3`, fell to 4.31 : 1 on the strip's raised surface in
   light, so on raised surfaces it now keeps its line's colour; (b) the selected-place tint was a
   `color-mix()`, whose computed value is `oklab(…)`, and the lab's contrast check read that as
   near-black (1.15 : 1). The text was legible, but the check could not see that. The tints are
   hex now, as V1's generated tokens are, and **a production token must be hex** for the same
   reason. The first run also caught variant A picking up the pass, which would have moved the
   baseline. A is excluded and was re-measured.

## 6. Cost and LD-1

The pass is **1.30 KB marginal, gross**. Most of it restyles rules that production replaces
(rows, tabs, strip, header, decision bar) rather than adding to them, so the net is lower and is
owed until production nets it against the V1 rules it supersedes. It is product presentation,
not visual behaviour, so under LD-1's recommendation it sits **under the V1 bundle gate with the
information layer** (≈ 3 KB → ≈ 4.3 KB gross). **The 12.5 KB visual-behaviour figure is
unchanged.** R3's +0.11 KB rounds into it (≈ 12.6).

## 5. Owed, not done

- **Residual orphan:** on the phone, "all missions" in the Today line wraps between its two words
  (`white-space: nowrap` on that link; left unchanged so the measured state is the recorded one).
- **Skip link** (F-15): every hash link re-routes in the lab, so a skip link needs a focus handler,
  not an anchor; it belongs in production's router. Recorded for P-2.
- **The capsule and the strip's shadow in Qt**: Chromium only so far. A `box-shadow` is not one of
  the readback properties, but it is a paint, and it sits on fixed chrome; the Qt scan-out glance
  (A §T.2) should include it.
- **Human gates**: H-1 (5 s), H-2 (decision comprehension) and H-3 (thumb test) now run on the
  polished lab; `?dp=0` is available if the user wants a before/after arm.
