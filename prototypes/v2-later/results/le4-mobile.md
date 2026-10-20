# LE-4: the phone as a phone (LD-2, LD-5, LD-7) (2026-10-05)

**Result: PASS on every automated measure; the physical-phone thumb test (H-3) is the gate.** The
phone stops being thousands of pixels tall (Now 4,336 → 1,206 px; the D-1 diagnosis state
5,066 → 844 px, one screen), the e-stop is visible without scrolling on every phone screen, a
decision is a full page with a fixed bottom bar, and Back never leaves the app. All of it is
layout, language and ≈ 0.7 KB of CSS + push (`le6`).

Lab: `lab/ia.html?v=b` at 390 × 844 and 360 × 740 (touch, DPR 2). Probe: `tools/ia_probe.py`
(`phone_flows`, `screens`). Captures: `results/le1/shots/b_phone_*.png`, `a_phone_*.png`.

## 1. Composition

Header (52 px: mark · compose · **Stop all**) → content → **mission strip** (56 px, two lines,
fixed) → **three tabs** (56 px: Now · Needs you · Missions). Control goes behind the header menu.
Under a decision page the strip and tabs are hidden so the decision bar owns the bottom edge.

## 2. Measured

| Measure | A (V1 structure) | B (proposed) |
|---|---:|---:|
| Now height, busy fixture | 4,336 px (5.1 screens) | **1,206 px (1.4)** |
| Now height, diagnosis state (4 approvals, nothing running) | 5,066 px (6.0); real V1 5,590 | **844 px (1.0)** |
| Needs you / Attention height | 2,555 px (3.0) | **902 px (1.1)** |
| Longest decision page | (sheet over Now) | 1,481 px (1.75), bar always visible |
| E-stop visible without scrolling, 6 screens (Now, Needs you, Missions, two missions, a decision) | 0 of 4 measured screens | **6 of 6**, including after scrolling to the bottom |
| Decision bar buttons | — | Reject 58 × 103 · Ask for changes 58 × 103 · Approve 58 × 136 px; 10 px above the edge |
| Back from a decision | — | returns to Now; stays in the app |
| E-stop: first press | (modal dialog) | **arms** ("Press again to stop all", announced politely) |
| E-stop: after 3 s untouched | — | **lapses** back to "Stop all" |
| E-stop: two presses | dialog → confirm | **engaged** ("Stopped · re-arm in Control"); **0 dialogs** opened |
| Targets < 44 px (excluding inline text links) | 15–20 per screen | 3 → **0** after fixes (mark, two-line row links, `summary`, the "output" link) |
| axe WCAG 2.2 AA violations (dark, light, high contrast, forced) | 1 (an unlabelled priority field) | **0** |
| Horizontal scroll at 200 % text | none | none; rows wrap, the strip wraps, decision buttons stack |
| Small phone 360 × 740: Now | 4,546 px (6.1) | 1,224 px (1.7) |

## 3. Findings the prototype forced

1. **Four lines per row was the first draft.** At 390 px a desktop-shaped Decide row ("Approve
   plan v2 for Deploy release notes to staging · … · expires in 8 min" + the context line) wrapped
   to four lines. Phone rows are now two: *verb · object* / *project · consequence · expiry*; the
   branch goes one level down.
2. **The strip truncated the title** in its first draft. It is two lines now; only the title may
   ellipsize, and only below 360 px; the step and elapsed never do.
3. **Targets:** the mark (18 × 24), two-line row links (42 px), `summary` (36 px) and the "output"
   link (22 px) were under 44 px; all fixed in `ia.css`.
4. **Nothing here needed motion.** The decision page push and Back are LE-5's `push`, measured
   separately; in reduced motion the page is instant and nothing else changes meaning.

## 4. Open — human gates

- **H-3** physical-phone thumb test (iOS Home Screen PWA and Android Chrome): one-handed approval,
  why-it-stopped, stop everything, Back.
- **H-4** e-stop hand check: is "armed" ever read as "stopped"?
- Not built here: privacy blur on background, offline never queuing a decision (O-20), passkey
  step-up (O-24), the header menu's contents.
