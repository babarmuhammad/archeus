# LE-7 (LD-8): warmer greys and the balance of the state colours — measured, nothing changed (2026-10-05)

**Result: measure-only, as LD-8 recommended — and the measurement argues against both halves of
the proposal as stated.** Warm neutrals can be had without breaking a single V1 contrast floor,
but at the chroma the research implies they move the ground to within 12° of the amber that is
reserved for "needs you". The state colours are already balanced in the light theme; in the dark
theme the imbalance that exists is the intended one (amber heaviest) plus one that is not
(failure lighter-weighted than success). No V1 token was edited. Tool: `tools/colour.py` →
`results/le7/colour.json` (OKLCH, WCAG contrast, ΔE OK × 100), over the V1 token values.

## 1. The six state colours, as built

| State | Dark L / C / H | Light L / C / H |
|---|---|---|
| active | 0.723 / 0.148 / 252 | 0.518 / 0.182 / 258 |
| **attention** (needs you) | **0.810** / 0.144 / 79 | 0.500 / 0.109 / 70 |
| blocked / failed | **0.701** / 0.157 / 19 | 0.501 / 0.178 / 29 |
| paused | 0.754 / 0.021 / 258 | 0.501 / 0.025 / 259 |
| thinking | 0.755 / 0.141 / 295 | 0.507 / 0.194 / 291 |
| done | 0.774 / 0.144 / 154 | 0.528 / 0.126 / 152 |
| **Lightness spread** | **0.109** | **0.028** |
| Minimum pair ΔE (×100) | 11.1 (active / thinking) | 10.8 (active / thinking) |
| Lowest state contrast on bg / surface-1 / surface-3 | 5.16 : 1 | 4.73 : 1 |

Reading it:

- **Light theme: already balanced** (spread 0.028 L). Nothing to do.
- **Dark theme: amber is the heaviest colour by design** — it is the single band for "needs you"
  and *should* win. Equalising it would weaken the one signal Archeus reserves.
- **Dark theme: blocked/failed is the lightest-weighted colour (L 0.70), below done (0.77).** A
  failure reads quieter than a success. That is the one real imbalance. Lifting blocked to ≈ 0.74
  L (same hue and chroma) would put it level with active; it is a token change, a contrast re-check
  and a ΔE re-check against attention (they are the two warm hues). **Proposed, not made.**
- **active / thinking is the closest pair** in both themes (ΔE ≈ 11). Shape separates them (PR-5),
  so colour does not have to; worth watching in the PR-5 identification test.

## 2. Warm neutrals

Every neutral was re-hued at its own OKLCH lightness (lightness held exactly, so contrast barely
moves). Two strengths:

| Variant | Ground (dark) | Chroma of ground | Ground hue vs amber | Text / bg | Text-3 / surface-3 | All V1 floors |
|---|---|---:|---:|---:|---:|---|
| V1 as built (steel) | `#0E1116` | 0.011 | 181° | 15.66 | 4.81 | pass |
| warm, hue 70 | `#14100C` | 0.010 | **12°** | 15.69 | 4.81 | pass |
| **charcoal**, hue 70, ≈ ⅓ chroma | `#13100E` | 0.0065 | 23° | 15.66 | 4.81 | pass |

Light theme: every variant passes too, but the warm and charcoal variants put `text-3` on `bg` at
exactly **4.50 : 1** — on the floor, with no margin.

Reading it:

- **The floors are not the obstacle; the amber is.** At the research's "hue 60–80" the ground
  shares the needs-you hue. A warm ground under an amber band is a lower-contrast *signal* even
  where the contrast *ratio* passes, because the band is distinguished from the ground by hue
  as well as lightness. That cannot be measured by a ratio; it needs eyes.
- **Charcoal** (one-third of V1's neutral chroma) keeps 23° of separation and reads as "less blue"
  rather than "brown". It is the only warm variant worth showing a person.

## 3. Classification

- LD-8 **measurement: done**. **Human test required** before any token change: the four grounds
  (steel, charcoal, warm) side by side with the amber band and a blocked row, dark and light, the
  user's eye. **No production change proposed** except, possibly, the blocked-lightness lift, and
  that only through V1's own token gates.
