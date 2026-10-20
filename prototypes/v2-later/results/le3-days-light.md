# LE-3: the day's light — what did Archeus actually touch today? (2026-10-05)

**Result: PASS WITH VARIANT for R3 (ledger + traces) as the day's light; R1 (lanes) is kept as a
World view, not as the signature; R2 (ledger alone) is the accessible mirror of both.** Every
representation passed the provenance gate (0 of 2,000+ drawn elements without a record, across 54
renders), parked completely after render, and cost under 3 ms to draw a 40-mission day. They
separate on what they *answer*. The human verdict — is R3 a noun Archeus can own, or just a
good list? — is open and is the actual gate (the two-week diary in LR §18).

Lab: `lab/light.html?r=quiet|lanes|ledger|hybrid` with `&day=yesterday` (a quiet day on the same
scale) and `&corpus=heavy` (40 missions over 6 projects). Probe: `tools/light_probe.py` →
`results/le3/probe.json`, captures in `results/le3/shots/` (desktop and phone × dark, light, high
contrast, forced colours, 200 % text; every representation × today, yesterday, heavy).

## 1. The representations

| | What is drawn | Built from |
|---|---|---|
| **quiet** (today's V1/V2) | The verdict sentence only | — |
| **R1 lanes** (LR §18 as specified) | A fixed 06:00–24:00 axis; one lane per project touched; one line per mission from its first to its last recorded event, reaching *now* if still open; the line's end is its outcome by **shape** (tied off ✓, cut ✕, wall │, needs-you ◆, review ring ○, open dot, planning dashed ring); a tick per checkpoint; a dotted *now* | mission/execution/verification/approval/checkpoint events + mission state |
| **R2 ledger** | Per project: each mission as figure + title + outcome in words + its time span; the project line gives files changed and checkpoints | the same |
| **R3 ledger + traces** | R2's sentences, each preceded by a word-sized trace of that mission on the **same fixed day axis** | the same |

Rules held by all three: **no colour without a shape** (outcome is legible in forced colours and
monochrome); every mark is a link to its mission (proof of life) and every SVG primitive carries
`data-src` naming the mission and event seqs it came from; **one scale across days**, so
yesterday's two missions look like a quiet day rather than being stretched to fill; static SVG,
no animation, no timer. The verdict is computed from the same states as Now — the first draft
said "All clear." over a day with three things waiting; that was a defect, now fixed.

## 2. Measured

| | quiet | R1 lanes | R2 ledger | R3 ledger + traces |
|---|---:|---:|---:|---:|
| Projects named without interaction | 0 / 3 | 3 / 3 | 3 / 3 | 3 / 3 |
| **Missions named without interaction** | 0 / 10 | **0 / 10** (titles only on hover/focus) | 10 / 10 | 10 / 10 |
| Outcome by shape | — | ✓ | ✓ (PR-5 figure) | ✓ |
| Outcome in words | — | — (only in the list mirror) | ✓ | ✓ |
| When (time of activity) | — | ✓ (axis) | ✓ (spans in text) | ✓ (traces) |
| Files changed | — | — (ticks only) | ✓ | ✓ |
| Words on screen | 9 | 35 | 119 | 98 |
| Drawn elements / without a record | 0 / 0 | 88 / **0** | 34 / **0** | 59 / **0** |
| Heavy day (40 missions): end marks overlapping | — | **0** | — | — |
| Heavy day height, phone | 844 | 844 | 1,710 | 1,621 |
| Render (ms, desktop, loaded machine) | 0.9 | 2.4 (2.6 heavy) | 1.2 | 1.2 (1.9 heavy) |
| After render: rAF calls / animations (1.5 s window) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| axe (WCAG 2.2 AA), dark / high contrast / forced | 0 | 0 | 0 | 0 |
| Horizontal scroll at 200 % text (desktop, phone) | no | no | no | no |
| **Marginal bundle cost** (minified, inside the V1 bundle; `le6`) | 0 | **1.65 KB** | **0.96 KB** | **1.57 KB** |

The gates were mutation-checked (`tools/mutate_gates.py`): an unsourced circle and a mark citing an
unknown mission are both counted.

## 3. Reading the result

- **The quiet state answers none of the question.** It is calm and it is empty: on a quiet day
  the product has nothing of its own on screen (LR §2 failure 7, confirmed).
- **R1 is the best picture and the worst answer.** It is the most recognisable object of the three
  and it scales cleanly to 40 missions with no overlaps, but it names no mission without a hover,
  says nothing about files, and with a fixed 18-hour axis at 15:12 nearly half of it is the empty
  rest of the day (that emptiness is honest — it is the one-scale rule working — but it is
  space). On a phone it gives 14 px to an hour. It also reads, to an unprimed eye, as a Gantt
  chart, which is the "dashboard of charts" the brief excludes. **Kept as World's day view, where
  a person goes to look at the shape of the day, not as the default.**
- **R2 answers everything and has no shape.** It is the most accessible and the cheapest, and it is
  a list. It stays as the text mirror of R1 and as the reduced/screen-reader form of R3.
- **R3 answers everything in fewer words than R2 and keeps a shape.** The traces carry *when* and
  *how it ended* at a glance and line up across rows because they share the axis; the sentences
  carry *what*. In forced colours the end shapes stay distinct (ticked, cut, walled, diamond,
  ring). It is a candidate noun, not a proven one.

## 4. Variant terms (if accepted)

1. **Placement:** Now's "all clear" state and the first open of the day (it is K-1's canvas); on
   demand from World. Never a permanent panel on a busy Now (that would be the dashboard).
2. **Grouping by project, ordered by the latest event;** the project line carries files changed.
3. **The axis window is a tuning parameter for the human test** (06–24 is what LR §18 implies;
   07–21 would give the traces 30 % more resolution at the cost of clamping late work).
4. **Never animates**, except as K-1's canvas during handover (already governed by PR-6).
5. **Planning and running must stay distinct by shape** — the first draft drew both as a filled
   dot, which forced colours collapsed; planning is now a dashed open ring (the PR-5 grammar).

## 5. What it needs that V1 does not serve

**DR-7.** `/v1/events` takes only `after` and `limit`, so a day's light today means paging the
whole log from a cursor and filtering by `at` in the client (the lab's `day()` does exactly that
over a fixture). A `since/until/project` filter, or a per-day aggregate, is the read this needs
(answers LQ-8: *not* drawable efficiently from today's reads). Files changed come from
`Checkpoint.files_changed`, which exists.

## 6. Open — human gates

- **Is R3 good enough to be a signature?** Show R1/R2/R3 cold to the user and ≥ 2 others: "what
  did Archeus touch today?" (time to answer, and whether they would look at it again).
- **Two-week diary** (the kill criterion in LR §18): demoted to a World view if it does not answer
  a question the user actually had.
