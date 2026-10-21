Serve with py -m http.server 8000, then open http://127.0.0.1:8000 (open a terminal in this folder first; file:// does not work for the PWA).

# Archeus V2 prototype (fake data, simulated chat)

A clickable prototype of the V2 living space. Plain HTML, CSS and Canvas 2D. No framework, no build step, no npm, no web fonts, no CDN.

## Round 10f phone (2026-10-22): Overview polish and the two sheets

Owner rules in this round: frame text at the concept's own sizes with an 11 CSS px floor (HIG). The owner-approved 10 px list
applies only to the sub-lines `label_review_plan`, `label_codex` and `label_verifying`. Tappable hit areas stay 44 pt without
changing the visible shapes. The Archeus name stays outside the big hull.

Masters. `phone-1-now-v2.png` is 804 x 1373 (402 x 686.5 CSS at DPR 2). `phone-2-decision-v2.png` and `phone-3-chat-v2.png` are
724 x 1573 each (the 804 x 1748 figure in the earlier brief is wrong; the sheets are 362 CSS wide at DPR 2). The floor is 22 units
in all three frames, which is 11 CSS px at each master width. At 360 px wide the frame scales down with the screen: Overview text
falls to 9.8 CSS px and sheet text to about 10.9 px. That is an owner decision (residual 9).

Overview (phone-1), what changed:
- Status line 22 units (was 31.4, the old 14 px rule). Ink mass 1.53 times the concept (was 1.87).
- Chip: the pill is the concept's 161 units (was about 230). Its text is 22 units with -2 units tracking, so "2 more projects"
  fits. At 11 px the text alone is about 164 units at natural spacing, so the tracking pays for the concept width.
- Review label: 22 units, weight 600, no halo. The halo came from `#s-now .ov-art text`, which beat `#s-now .ov-btn` on
  specificity; the Review and chip rules are now `.ov-art .ov-btn` and `.ov-art .ov-chip-text`.
- Glows: the amber diamond and the blue star are live SVG blur filters (`ov-glow`). Strength and blur are measured on the concept by
  `tools/fit_glow.py`: amber sigma 6.0, amplitude 0.161; blue sigma 4.0, amplitude 0.196. The same model is subtracted from the art
  (`fit_glow.subtract`), so each glow is drawn once.
- Review has no outside glow in the concept: the alpha stays within +/-0.01 out to 40 units, measured. Nothing is added. The
  owner's "Review rim glow" is not in the raster; this is an owner decision.
- Stop: the concept fill is a faint vertical gradient, #2C2932 at the top, #312C36 at the middle, #2F2B35 at the bottom (measured).
- Scene labels: Search provenance and Fix date test are 22 units (were 20.5 and 17.9). Review plan and Codex are the 20 unit
  sub-lines. Weights 400 (serif) and 350 (sans) match the concept's thinner strokes.

Decision sheet (phone-2, `#s-plan` on the phone, `art/phone-2-*`). The base art is the concept with the live text, marks and
controls removed, and the sheet area replaced by the page background (`tools/build_sheet_art.py`: per-column median of the band
above the sheet, smoothed). The sheet is the one tinted element and it is live: rgba(40, 34, 52, 0.25) with a 1 px top edge.
What / Why / Core consequence are SVG text at the measured ink boxes. Open decision is a full-width amber outline (live rect) with a
button over it. The steps are unchanged: Open decision opens the full review (`planOpened`), then Approve, then the step 2 confirm,
then the explicit confirm box (Cancel is the default). Tell and Stop sit above the home indicator.

Chat sheet (phone-3, `art/phone-3-*`). Focusing the Tell bar switches the Overview to the phone-3 frame (`data-frame="3"` on
`#s-now`). Bubbles are HTML on the phone-3 units: owner bubbles right-aligned (391 units), Archeus bubbles left (521 units). The
thread is seeded with the concept's fixture: you "Open a mission in Notes: Export backup", Archeus "Mission created in Notes. Start
it when you like.", the Start card for Export backup, you "What does exit code 137 mean?", then the General answer with its tag and
the off "Promote to project memory" switch. The tag "General" is shown in the General line; the raster has no visible tag there.
Back returns to the Overview frame.

Measured (`tools/compare_frame.py`, full resolution, no blur, DPR 2; mean absolute RGB difference, 0 to 255):

| Frame | Frame mean | Art (no live element) | Worst text | Notes |
|---|---|---|---|---|
| Overview, phone-1 (804 x 1373) | 4.63 (was 5.11) | 1.74 (was 2.12) | Fix date test 52.8 (was 21.4); Search provenance 30.1; Review plan 35.0 | Review fill 11.1 (was 28.6); chip 24.2 (was 35.6); status 37.5 (was 59.4) |
| Decision, phone-2 (724 x 1573) | 7.94 | 2.71 | Title 60.1; headline line 1 52.2 | open 11.2; bar 10.4; stop 15.1; header 11.4 |
| Chat, phone-3 (724 x 1573) | 11.22 | 5.13 | Start title 56.4; bubble body 40 to 60 | Start button 40.7 (was 127.7); header 12.6 |

Regional metrics: `tools/compare_phone.json`, `tools/compare_phone2.json`, `tools/compare_phone3.json`. Renders are at DPR 2:
402 x 687 viewport for phone-1, 362 x 787 for phone-2 and phone-3, so one unit is one device pixel.

Checks: `check.mjs` through the testlock. Round 10f assertions: the 11 px floor in each frame, the sub-line list, the chip width,
glow filters, the Stop gradient, the phone-2 and phone-3 art and layout, the decision flow, the seeded thread, and the service
worker cache `archeus-v2-proto-ph2`. Label overlap probe (Chromium, pairwise over live SVG text and HTML controls): no overlaps
between different items, except the three headline pairs already listed in round 10d (line boxes; the ink does not touch) and the
Open decision text under its own button. Decision flow: Open decision, then the review, then Approve, then the confirm box (return
value empty; Cancel is the default). Chat: focusing the Tell bar switches to the phone-3 frame.

Residual differences (measured where a number exists):
1. Serif glyph shapes: the concept's serif is narrower and lighter than Libre Caslon. Headline line 1 mean is 52.2 on phone-2
   (14.6 on phone-1, where the concept's word gaps were wide enough to place each word). At 402 px "needs" nearly touches "you".
   Not fixable with the vendored face.
2. Sans: Inter is wider than the concept's sans in the sheets. The title "Search provenance" (Inter 600, -4 units tracking) is 60.1.
3. Labels at the 11 px floor are larger than the concept's: Fix date test +22 units of size (mean 52.8). Review plan and Codex at
   the 10 px sub-line size are wider than the concept's 8 px text (means 35 and 24).
4. Chip tracking -2 units (about -1 CSS px): the price of the concept's 161-unit width at 11 px.
5. Review has no outside glow in the concept, so none is drawn. Owner decision.
6. Phone-3 bubble text sits 2 to 13 units off the concept's ink on x and 4 to 13 units on y, because the bubbles are flow layout,
   not absolute baselines. Body text means 40 to 60.
7. Phone-3 Start title is 26 units narrower than the concept's (serif face).
8. The art region of phone-3 (mean 5.13) includes the sheet's tinted background, which is a flat approximation of the concept's
   sheet (the concept's sheet has a faint gradient).
9. At 360 px wide the Overview text is 9.8 CSS px, below the floor. If the owner wants 11 px at 360, the frame text grows to
   24.6 units and the chip grows to about 200 units.
10. Not verified: a real device (safe areas and the home indicator are emulated), iOS and Android rasterisers, a second DPR, and
    the sheets at widths other than 362 and 402 (the frame scales; it is not re-laid out).

## Round 10d phone (hybrid, 2026-10-22): concept raster as the art, live layer on top

Method (owner decision, hybrid): the scene picture is the concept raster itself. Every live element was removed from it and the cleaned raster is the base art. Everything live sits on top at the concept's measured units: text (vendored fonts), the mission marks (live SVG shapes in the concept's own geometry, coloured from the data model), the Review button, the chip, the Tell bar and Stop. One owner per visual element: a removed element is never drawn twice.

Files:
- `art/phone-1-base.webp`: 804 x 1973 units. The concept (804 x 1373) with the live content removed and 300 units of background above and below, extended from the edge rows (smoothed along the row). Lossy WebP at quality 100, 114 KB. A lossless WebP is 618 KB, over the 400 KB budget.
- `art/phone-1-layout.js`: measured ink boxes of each text, mark and control in concept units, and the edge colours.
- `art/phone-1-type.js`: size, tracking, weight, origin and per-word x of each live text (from `tools/fit_type.py`).
- `fonts/`: LibreCaslon Text (serif, variable wght 400 to 700) and Inter (sans, variable), both SIL OFL 1.1, with licence texts, URLs and sha256 in `fonts/README.md`.

Regenerate: `py -I tools/build_phone_art.py "D:\hub-concepts-codex4\phone-1-now-v2.png"` writes the three art files. Config: `tools/trace_phone.json` (what to remove, what to measure). Offsets: `tools/type_offsets.json` (tracking and origin corrections, set from the compare step). Compare: `py -I tools/compare_frame.py <concept.png> <render.png> tools/compare_phone.json <out_dir> <label>` prints the ink-box alignment table, the regional metrics and the ten worst 48 px blocks, and writes the diff x4, the 50 % blend, the alpha overlay and lossless PNGs for alternation.

Font choice (from the bake-off in `D:\fontbake\results.md`, no free font matched the concept serif, best mean IoU 0.47): serif = Libre Caslon Text, weight 500 (headline 500, labels 500, wordmark 500). Sans = Inter, weight 350 to 600, kept over Source Sans 3 (weight 400): on the sans regions Inter has the lower mean error (status, fixture, labels, chip, Review, Tell and Stop: mean 23.2 against 24.9 for Source Sans 3 with the same fit), and its widths are closer on the fixture line. Source Sans 3 was removed from the folder. Both serif and sans sizes come from the concept's ink heights; the headline solves to 63.6 units, which matches the bake-off's 63.23 px.

What was removed from the art (`tools/trace_concept.py`): the wordmark, CONCEPT FIXTURE, the status line and dot, both headline lines, the three scene labels, the chip, the Review button and its label, the Tell bar and its placeholder, Stop, the amber diamond, the blue four-point star, the Codex triangle and the two Notes glyphs. The removed pixels are filled by harmonic interpolation from a 2 px ring outside the removed area. A wider ring picked up the glyph shadows and left blotches. Mesh threads that cross a removed glyph are redrawn from the neighbouring strokes (three bridges, across the glyphs of "Search provenance" and "Fix date test").

Verification. Frame at 402 css wide, DPR 2, viewport 402 x 687 so the 402 x 686.5 frame sits at 0. Screenshot 804 x 1373, unblurred, no resampling. Concept and render compared pixel for pixel. Measured numbers, not visual estimates:

| Region | Mean abs (RGB) | p99 (max channel) | Pixels > 24 |
|---|---|---|---|
| Frame, all pixels | 5.11 | 168 | 4.74 % |
| Scene (art plus marks) | 4.71 | 140 | 4.73 % |
| Header (wordmark to headline) | 10.52 | 224 | 7.73 % |
| Art, outside every live box (padded 12 px) | 2.12 | 43 | 1.97 % |
| Headline line 1 / line 2 | 14.6 / 22.5 | 219 / 238 | 11.4 / 16.5 % |
| Scene labels: Search provenance / Review plan / Fix date test / Codex | 22.4 / 19.1 / 21.4 / 11.6 | | |
| Marks: amber diamond / blue star / Codex triangle / Notes diamond / Notes star | 16.4 / 9.0 / 6.8 / 15.7 / 11.4 | | |
| Controls: Review fill / Tell bar / Stop / chip | 28.6 / 7.8 / 15.4 / 35.6 | | |

Registration. The art region is the one place where the frame can be checked without live text. Two references. The concept PNG shown 1:1 in the same Chromium pipeline, with no art and no live layer, scores 1.20 mean against the file: that is the screenshot floor. The decoded WebP scores 0.73 against the concept. The render scores 1.59 with the live layer hidden and 2.12 with it shown; the difference is the text halo, which belongs to the live layer. A one-pixel shift makes the art worse in both directions. So the art is registered to the master within the pipeline's own noise.

Text alignment. The ink box of every live text lands within 1 to 3 px of the concept's ink box at 804 units (alignment table from `compare_frame.py`), after a per-word x from the concept: the headline and the labels are placed word by word. The remaining text error is glyph shape, letter spacing inside words and anti-aliasing. The concept's serif is a Garamond-like face with its own letter shapes; no open face matches it, and Libre Caslon is the best of those tested in the bake-off and in this overlay. The wordmark is the weakest text (mean 47.5): its caps are tracked wider than the font's, so the letter positions inside the word drift.

Approved deviations (owner rules that conflict with the concept's own sizes, listed so the owner can say otherwise):
1. Body and tappable text is 14 css px at 360 wide (31.4 units), so 15.7 px at 402. The concept's status line is about 10.7 px, its chip text about 8.3 px and its Review label about 10 px. The status line and the chip are therefore wider than the concept (the chip is about 230 units wide against 161). Review and Stop are larger than the concept's type.
2. Scene labels keep the concept's sizes: Search provenance 22.4 units (about 11.2 px at 402), Review plan 16.8 units (about 8.4 px), Fix date test 20.7 units (about 10.3 px), Codex 15.9 units (about 8 px). These are below the 12 px scene floor because the concept is smaller; the owner rule says use the concept size and report it. The mission titles are tappable through their marks (88 unit hit circles).
3. CONCEPT FIXTURE keeps the concept size (17.2 units, about 8.6 px at 402).
4. Project names: Notes and Ideas sit on empty concept space beside their hulls (Notes centred at x 650, baseline 326; Ideas centred at x 684, baseline 1118), 24 units (12 px at 402). Archeus is outside the big hull, centred at x 88, baseline 486. No 14 unit clear span exists inside the big hull: its interior is crossed by threads at every position tested. The name sits on the empty space above the hull's upper-left edge.
5. The hamburger is gone. Places opens from the wordmark: a transparent 336 x 88 unit button over ARCHEUS (44 css px tall).

Layout. The frame is 1:1 at 402 wide (804 x 1373 units). The header is anchored to the top of the screen; the Tell bar and Stop are anchored to the bottom (bottom edge 99 units above the screen bottom, plus the safe-area inset); the art is centred vertically between them. On a taller phone the extra height is background, extended from the art's edge rows, so no band shows. Measured at 360 x 800, 390 x 844, 393 x 852, 402 x 874, 430 x 932 and 440 x 956: the same composition at every width, no horizontal scroll (scrollWidth equals the viewport), bar and Stop above the bottom edge.

Behaviour, kept apart from the visual score. Tap on each mission mark opens its detail (checked at 402 x 874). Review links to `#/plan/m-search`. The chip opens the project list. Stop and the Tell input work (a sent message appears in the feed). Enter and Space on the SVG buttons still dispatch clicks. Reduced motion and `?nocolor` are unchanged. The two-step decision screen is unchanged.

Label overlap probe (every SVG text and HTML control in the overview, pairwise, Chromium, six widths). Zero overlaps between different live items. The only pairs reported are three inside the headline (`1`/`1`, `needs`/`verifying`, `you`/`verifying`). Their line boxes overlap by a few units while the ink does not; the concept's own ink boxes overlap the same way (line 1 ends at y 348, line 2 starts at y 344, at different x).

Hit areas, css px: Review 96 x 44, chip 127 x 44, mission marks 44 x 44, Notes marks 44 x 44, Places 168 x 44, Stop 81 x 50, Tell input 280 x 48.

Residual differences (numbered, with the measured number):
1. Serif glyph shapes and letter spacing: wordmark mean 47.5, headline 14.6 and 22.5, labels 11.6 to 22.4. The concept has coloured fringes (ClearType-like); this render is greyscale. Not fixable with an open face that is not the concept's.
2. Status line: mean 59.4, ink mass 1.87 times the concept's (14 px rule, deviation 1).
3. Chip: mean 35.6, about 230 units wide against 161 (deviation 1). Its text is 14 px.
4. Review: fill mean 28.6, label mean 40.8 (deviation 1). The concept's glow under the button is not drawn; the art keeps the concept's glow outside the button. The worst 48 px blocks of the frame sit at y 792, on this label.
5. Mission marks: the concept's glow around the amber diamond and the blue star is not drawn (diamond 16.4, Notes diamond 15.7, Notes star 11.4, blue star 9.0).
6. Stop: mean 15.4. Its label is 15.7 px (deviation 1). The button fill is a flat #2F2B35.
7. Art edges: the Review button leaves a 2 px ring of concept glow in the art (it is not removed). The Tell bar and Stop outlines are drawn live, so the concept's outlines are replaced rather than matched.
8. Threads that cross a removed shadow are not redrawn. The art has no thread through the middle of "Search provenance" (about 4 units at the caps).
9. The art is lossy WebP (0.73 mean against the master on its own).
10. The Archeus name sits outside the big hull (deviation 4).

Not verified: a real device (safe areas and the home indicator are emulated with the bottom margin only); iOS and Android rasterisers (the comparison is Chromium on Windows); the chat sheet and the phone-2 and phone-3 views (only the Overview was compared); a second DPR (the metric is DPR 2 only).

## Round 10c phone (2026-10-21): one SVG frame in the concept's own units

Status: PARTIAL against the owner's bar ("exactly the design prototype"). The phone Overview is now a hand-authored SVG that matches the concept's composition closely at 402 x 874. The differences that remain are listed below with numbers. Desktop, Replay, terminal, Mission, Shared and the phone-2 and phone-3 views are unchanged in this round.

Concept file: `D:\hub-concepts-codex4\phone-1-now-v2.png` is 804 x 1373 px (402 x 686.5 CSS px at DPR 2), not 804 x 1748 as the round brief stated. The 1373 height was already noted in round 10b. The frame keeps the concept's own aspect: it is scaled to the screen width, centred, and letterboxed vertically with the page background.

What was traced: every scene position is read from labelled grid crops of the concept (x and y in the concept's pixels; one unit = one concept pixel = half a CSS px at 402 wide). The layout table is `OV` in app.js, keyed by project and mission ids:
- Archeus hull: 13 vertices (42,683) (142,544) (319,450) (599,595) (714,666) (764,763) (731,834) (645,884) (541,998) (432,961) (376,1030) (269,975) (96,872). The brief's "about 10 vertices" is not what the image shows; the outline keeps 13. The point (432,459) is an interior node, not a corner.
- Amber hull (Search provenance, m-search): 7 vertices, enlarged from round 10b so that 32-unit labels fit inside (see the type rule below).
- Blue hull (Fix date test, m-date): 7 vertices, sharing four vertices with the Archeus hull.
- Notes and Ideas hulls: 6 vertices each. Glyphs in Notes: m-index (diamond) and m-read (star).
- Star centre (431,697): one vertical thread (432,459) to (432,961), a horizontal ray, four diagonal rays, 26 radial threads, a bright knot.
- Headline, wordmark, status line, bar (36,1176) 560 x 100, Stop (611 to 770), chip (354,1052) 236 x 48, names Notes (650,322), Ideas (684,1122), Archeus (262,566).

Type rule: the concept's smallest text is about 12 units (about 9 CSS px at 402). The 14 CSS px floor at 360 wide needs 32 units (scale 360/804 = 0.448). So every scene label is 32 units or more, and the labels were enlarged. Consequences: the amber hull is larger than the concept's; "CONCEPT FIXTURE" and the status line are larger; the amber and blue labels were re-spaced to keep them apart.

Hulls are neutral ivory outlines with value-stepped facets (a fan from an anchor to each edge; in the big hull, one interior point per face), three opacity tiers for the thin lines, and a small dot on each interior point. Colour is only on the two missions: amber for Search provenance and blue for Fix date test.

Labels: SVG text with a dark halo (paint-order stroke) instead of boxes, so a facet line can pass behind a word without touching it. Overlap probe (`overlap.py`, Chromium, every SVG text and phone control box, pairwise): zero overlaps at 360, 390, 402 and 440 CSS px.

Touch: the Review link has a 44 px hit box around its visual; the mission marks are 52-unit hit circles (at least 44 CSS px at 360); the chip has a hit box 100 units tall; the Stop button and the bar are 100 units (44.8 CSS px at 360, 50 at 402).

Scene interaction: a hull or a mission opens the detail sheet (as in round 10b); Review links to the decision (`#/plan/m-search`); the chip opens the project list. Keyboard: Enter and Space activate the SVG buttons. Reduced motion: the scene is static (no motion work this round).

Similarity (sim3.py: concept and proto frame at 160 px wide, blurred; lower is closer; amber and blue are the warm and cool channels; edge overlap is the share of matched edges, higher is closer):

| Iteration | Change | Lum MAD | Amber MAD | Blue MAD | Edge overlap |
|---|---|---|---|---|---|
| 1 | first SVG, frame not yet cropped to the concept ratio | 12.37 | 0.66 | 2.07 | 55.3 % |
| 2 | frame cropped to concept ratio | 8.02 | 0.64 | 1.78 | 81.7 % |
| 3 | amber hull enlarged, chip moved, Stop ivory | 7.80 | 0.83 | 1.75 | 81.3 % |
| 4 | facet fills per hull, star rays, label baselines | 7.55 | 0.92 | 2.05 | 80.4 % |
| 5 | diamond and label spacing, halo weight | 7.75 | 1.01 | 2.06 | 80.0 % |
| 6 | big-hull interior dots, wordmark shift | 7.68 | 0.99 | 2.04 | 81.0 % |
| 7 | status line, blue fill, overlay check | 7.63 | 0.99 | 1.86 | 79.5 % |
| 8 | Archeus outline without the (432,459) corner, label offsets | 7.49 | 0.97 | 1.87 | 82.4 % |
| 9 | star spread and a heavier big-hull fill (reverted in 10) | 8.31 | 0.99 | 1.79 | 82.9 % |
| 10 | hull fill reverted, all widths rendered | 7.60 | 0.97 | 1.87 | 82.8 % |
| 11 | label spacing after the overlap probe | 7.68 | 1.28 | 1.89 | 82.2 % |
| 12 | labels 32 units (14 CSS px rule) | 7.79 | 1.28 | 1.89 | 81.8 % |
| 13 | amber and blue labels re-spaced; probe clean | 7.89 | 1.46 | 1.89 | 80.9 % |
| 14 | chip rect scoped (its hit box no longer tinted) | 7.90 | 1.46 | 1.89 | 81.0 % |

Reading: the luminance MAD sits between 7.5 and 7.9 from iteration 2 on. The amber MAD rose once the labels were enlarged and the amber hull grew, so it tracks label size, not hull shape. The metrics do not separate the iterations; the montage and the colour-fringe overlay (concept red, render cyan) drove each change. Treat the numbers as a sanity check only.

Checks:
- `check.mjs` through the testlock: round 10c assertions added (frame ratio and viewBox, CONCEPT FIXTURE, OV keys, decision link, chip formula, no scene label below 32 units, Stop and bar at least 100 units). Passes: references, manifest, parse, 14 contrast pairs, minimum font 14 px.
- Six widths (360, 390, 393, 402, 430, 440) rendered at DPR 2 and seen in one montage: the same composition at every width, centred, letterboxed vertically, bar above the bottom edge, no horizontal scroll.
- Desktop 1440 x 900 rendered: canvas scene unchanged. Phone `#/now` at 402 x 874 rendered with no page errors.

Differences left (numbered; the first three are the ones a reviewer sees first):
1. Typography: the concept's serif is a Garamond-like face; the prototype uses the system serif (Palatino or Georgia on Windows). The headline is about 4 % wider and the wordmark about 6 % wider than the concept at the same cap height.
2. Label size: every scene label is larger than the concept (32 units against 22 to 26 in the concept). The amber and blue hulls are sized for them, so their outlines are larger (amber hull spans x 72 to 378 against 92 to 352).
3. Status and fixture lines: the status line and "CONCEPT FIXTURE" are both 32 units (the concept's are about 22 and 18).
4. Facets: the concept's big hull is a denser web of thin lines with lighter upper-left facets; the render has fewer, larger value steps.
5. The star: the concept's knot is brighter and its rays longer and more even; the render's rays are shorter and uneven.
6. Names: "Archeus" is a small label inside the big hull (the concept has none); Notes and Ideas are named outside their hulls, as the owner asked.
7. Chip: "2 more projects" is 236 units wide (the concept's is about 161), set lower and left to clear the 32-unit text.
8. Vertical placement: the frame is centred, so on a 402 x 874 screen there are 94 CSS px of background above and below the concept's own proportions. The bar sits at 682 to 732 CSS px, above the home indicator.
9. Review button: 163 x 49 units with a 32-unit label; the concept's button text is smaller.
10. Bar: 560 x 100 units (the concept's is 560 x 96), so Stop and the input reach 44 CSS px at 360 wide.

Not verified:
- A real phone: safe areas, Dynamic Island and home indicator are CSS only.
- iPhone 18 sizes; web fonts (none are loaded); Dynamic Type; screen readers beyond the aria labels.
- Colours were sampled from small neighbourhoods; no colour-managed comparison.
- Phone-2 and phone-3 views and the phone chat sheet (only the Overview was rendered this round).

Service worker cache bumped to `archeus-v2-proto-12`.

## Round 10b (partial, 2026-10-21): measured layout, desktop and phone Overview

Status: PARTIAL. Done in this round: the Overview scene is driven from a measured table (`CONCEPT_LAYOUT` in app.js), read from labelled grid overlays of desktop-1-now-v2.png (1296 x 729) and phone-1-now-v2.png (804 x 1373; the concept file is 804 x 1373, not 1748 tall). Not done: phone-2 and phone-3 comparisons and montages, four iterations for those, the 6 x 2 DPR render sweep, the Replay, terminal, Mission and Shared views (10c), motion (round 11).

Layout: hulls are the traced outlines (Archeus 10 vertices, Notes 8, Ideas 5 on desktop; on the phone the big Archeus outline, the amber Search provenance hull, the blue Fix date test sub-hull, Notes and Ideas as receded hulls). Each hull has about 30 to 40 thin facet lines in three opacity tiers (far tier fainter), a value step per facet, and vertex points. The star is 88 threads with a brighter knot and a thin vertical thread. The desktop scene uses 82 % of the stage width; the phone scene uses 94 %.

Other changes in this round: the desktop kicker reads NOW; the lede is the two-line concept text; the chat rows have a left label column (You, Archeus); the phone headline breaks after the middle dot; the phone prototype label is grey; Places is a quiet icon; Stop sits beside the bar; the phone chip reads "2 more projects"; the phone labels are smaller.

Similarity (sim.py: both images to 200 px wide, blurred luminance, mean absolute difference; lower is closer):
- Desktop 1600 x 900 vs desktop-1-now-v2: i1 7.64 (97.0 %), i2 7.95 (96.9 %), i3 7.95 (96.9 %). Not decreasing: this metric is dominated by the dark background, so it does not separate the iterations. It is not a reliable target.
- Phone 402 x 874 vs phone-1-now-v2 (scaled to the concept's aspect): i1 20.39 (92.0 %), i2 20.27 (92.1 %), i3 20.18 (92.1 %), i4 20.17 (92.1 %). Falling, but by under 0.3 %.

Overlap probe (label boxes, Chromium): desktop 1440, 1600, 1920 and 1280 clean; at 1600 x 900 the Replay verb labels "contains" and "executes" were hidden below 1700 px. Phone 360 to 440: one pair remains, the Archeus project label with the Codex label (also with Fix date test at 402 and 430). This breaks the zero-overlap rule. Not fixed.

Checks: check.mjs through the testlock (see the round 10b commit). Service worker cache bumped to `archeus-v2-proto-11`.

Still differs from the concept (measured by eye at 1600 x 900 and 402 x 874):
- Desktop: the Archeus hull is smaller in the frame than the concept (about 60 % of the stage width against 80 %), the star knot is a little smaller, the chat rows still differ in spacing, the Notes hull's missions sit near its edges.
- Phone: the composition is still denser at its centre; the amber hull and blue sub-hull are present but thinner than the concept's; the Codex label collides with the Archeus project label (open rule violation).
- Phone-2 and phone-3: not compared in this round.

## Round 10 (partial, 2026-10-21): concept fixtures and neutral hulls

Status: PARTIAL. The owner asked for an exact match to the six Codex v2 concepts, with at least four loop iterations per surface. This round did one loop on the desktop Overview and one on the phone Overview. Replay, terminal, Mission (03), Shared (06), phone-2 and phone-3 were not brought to the concept. Mention in the report, not as done.

- Fixtures now follow the concepts: projects Archeus (Search provenance, Fix date test, Docs refresh), Notes (Offline capture, Export backup), Ideas (no missions, "Early concepts."). Harbor and Lantern are gone; their two Lantern missions are removed. Atlas is still created from chat.
- Headline copy: "1 needs you · 1 verifying" with a middle dot.
- Hulls are neutral ivory outlines with value-stepped facets and a receded inner outline; project colours are removed. Colour is only on missions: amber for the owner's obligation, blue for live work, grey for done and idle. Green is kept for verified records only.
- Mission marks are small glyphs (amber diamond, blue star, grey diamond); the Codex execution is a triangle with the code glyph; Verification and Results are blue dots on the chain. The green check badges and the dashed circle around the amber mission are removed.
- The star is many fine ivory threads (44), not six rays. The orbit rings are removed.
- Desktop: the Overview positions follow the concept's layout (fixed outlines for Archeus, Notes and Ideas; fixed mission positions). The chat transcript is seeded with the concept's exchange and the Start card. The bar has an attach icon and a round send button. The rail has Now, Projects, Replay and a More group. The status line is grey; amber is used only for the obligation.
- Phone: the Overview uses a compressed concept layout (Archeus outline, amber Search provenance, blue Fix date test with the Codex triangle, Notes and Ideas named). It is still far from phone-1: the amber inner hull and the blue sub-hull are not drawn yet, the receded hulls are at the wrong positions, the headline is one line, and the Places button is not yet a quiet icon.
- Label budget: every mission is labelled on the overview (the budget only hides labels above 12 identities). The "+N more" note is no longer shown.

Known differences (not fixed in this round, measured by eye on the desktop montage at 1600 x 900):
- Constellation scale: the Archeus outline spans about 60 % of the stage width; the concept spans about 80 %.
- Facet density: the concept has many thin facet lines; the prototype has five or six broad facets with value steps.
- Star threads: the concept's star is denser and reads as a crisp knot; the prototype's is sparser.
- Chat feed: the rows use the concept's text but without the left label column.
- Replay, terminal, mission and shared views: not reworked to the concepts in round 10.

Service worker cache bumped to `archeus-v2-proto-10`. `check.mjs` passes through the testlock (font floor 14 px, contrast pairs, references).

## What round 9 changed

Owner answer, 2026-10-21 (verbatim): "Apply all five (Recommended)" on the five open questions of round 8. Applied: Replay verb labels hidden below 1600 px; terminal state colour; the decision as its own two-step screen on desktop and phone; the phone chat opens at the newest Start card; receded phone hulls keep their names only.

- **Replay.** Verb labels ("orchestrates", "contains", "executes") are hidden below 1600 px. Above 1600 they sit off the link (perpendicular offset). A faint hull now surrounds the mission node, so the mission reads as a project member as in replay-2.
- **Terminal colour.** State words and glyphs carry the approved palette: amber for needs-you, blue for running and verifying, green for done and verified, ivory neutral. Colour is a second cue; every state keeps its glyph and word. The tell line and the SIMULATED line are dimmed. A web page cannot read the NO_COLOR shell variable, so the prototype honours `?nocolor` in the URL and the `C` key. The 80 x 24 layout has the Why line on its own row.
- **Decision, two steps (desktop and phone, same page).** Step 1 is the decision: What, Why, the core consequence (fixture text), the action hash and plan version. "Review and approve…" opens step 2, a confirm screen with the mission, project, plan version and action hash. Its button opens the explicit confirm box (Cancel is the default). Nothing is approved; the confirm box is a fake. "Back to decision" returns to step 1. The page header hides on step 2 so only one headline shows. Terminal: `a` opens the confirm line, `y` confirms (fake), any other key cancels.
- **Phone chat.** Opening the conversation scrolls to the newest Start card, with the General thread below it. While the card is among the last three messages, new replies do not push it out of view. Start is amber filled, Keep as mission amber outline (as phone-3).
- **Phone hulls.** Receded projects are named only (no count line). The Codex triangle on the phone carries a small label, "Codex · execution".
- **Project list sheet.** The "All work" sheet lists every project by name (dot, name) with its missions under it. The rest chip (names beyond the fourth project when more than five exist) opens the same sheet. Not tested with more than five projects: the prototype has three fixture projects plus Atlas from chat.
- **Desktop calmer.** Project hulls use a lighter fill, with per-facet value steps (no gloss). The Review action is a small amber outline button (36 px), not a block; the phone keeps a filled 48 px button. The starfield sits at 55 % opacity.
- **Phone Open decision** is an amber outline button in the detail sheet (phone-2).
- **Mission and Shared.** Mission: the mission body is larger (112 px at full scale) so it reads as the centre of the view, closer to 03-mission. Shared: the Overview tab carries the evidence rows (Project files, Notes, Agent logs, Build outputs, Related content) as in 06-shared.
- **Typography (typography skill, applied).** Serif only for the wordmark, the headlines and the Archeus name. UI and label text is sans. Caps (kickers) tracked at 0.12 em (was 0.16 em, above the 5 to 12 % rule). Kerning on for the page. Sheet and chat text set to a 65 character measure and 23 px line height for body (about 1.45). Scale: wordmark serif 18 to 20 px, tracked caps; headline serif 34 px phone and 56 px desktop; sheet title serif 26 / 32; label title sans 19 / 24 (phone 22 / 28); label sub sans 14 / 20 (phone 16 / 22); kicker sans 600 14 / 20 caps; body sans 16 / 23; small sans 14 / 20; chips and buttons sans 14 to 16 / 20, weight 500; terminal mono 15 / 20. Minimum text size 14 px (check.mjs).
- **Design-audit (applied by hand, as in round 8).** Dimensions re-checked on the round 9 screenshots: hierarchy (one headline per screen, Review outranks the label), spacing (the phone bar and chips clear the home-indicator inset), type (the scale above), colour (amber means needs-you only; blue running; green done), density (duplicate Why line removed from the terminal and the second page headline on step 2 removed). The audit's approval step was not run.
- Service worker cache bumped to `archeus-v2-proto-9`. `check.mjs` adds round 9 assertions (two-step decision, NO_COLOR and colour, Codex phone label and chat open at the card).

### Sizes and checks (round 9)

- Phone Overview at 360 x 800, 390 x 844, 393 x 852, 402 x 874, 430 x 932 and 440 x 956: seen by eye in one montage (`scratchpad/t123/r9-phone-sizes-montage.png`). Every size shows the focus hull, the labelled Codex triangle, the amber Review button, the named receded hulls, and the bar above the bottom inset. No horizontal scroll. Label boxes: zero overlaps on the Overview at every phone width.
- Desktop Overview at 1280 x 720, 1440 x 900, 1600 x 900 and 1920 x 1080: seen by eye in one montage (`scratchpad/t123/r9-desktop-montage.png`). Label boxes: zero overlaps at all four sizes; project names present (Harbor, Notes, Lantern).
- Desktop Replay: zero overlaps at 1280 x 720, 1440 x 900 and 1920 x 1080. At 1600 x 900, "Archeus x orchestrates" and "Results x verifies" still touch (the verb labels are shown from 1600 px up). On phone widths, "Harbor" (the project name on the hull) overlaps "Results" (and "Verification" at 430 and 440). Not fixed in round 9: the project name wins the budget, so the record label should yield. Recorded as a gap.
- Terminal 120 x 40 (overview, mission, decision, Replay, plain-line, help) and 80 x 24 overview: seen by eye. The state colours and the dimmed tell line are visible in the screenshot.
- check.mjs via testlock: passes (references, syntax, manifest, 14 contrast pairs, minimum 14 px, round 9 assertions).
- The dim tell line and the colour contrast were checked in the screenshot and in the palette pairs only, not on a rendered pixel sample.

### Still weaker than the images (after round 9)

- Phone-1: facets now have value steps, but the composition is still denser than the image; the hull edges are bright and the star rays are long. Not matte in the strict sense (no per-facet lighting).
- Phone-2: the Open decision button is an amber outline; the sheet is a bit taller than the concept (the Core line is longer).
- Phone-3: the Start card is visible first, with the General thread below; the feed header is minimal and the grabber is small.
- Desktop-1: calmer, with lighter hulls and a smaller Review; the Archeus star is larger than in the image and the chat intro still sits near the scene at 1280 x 720.
- Replay: the faint hull is there; the verb labels are hidden below 1600 px; the phone overlap (project name over record label) is open.
- Terminal: colours follow the approved palette; the 80 x 24 layout is a stacked list, not the boxed concept.
- Mission (03) and Shared (06): both moved toward the concept (larger mission body; evidence rows). Still weaker: the phase stepper is a grid of dots rather than a connected line with checks, and the agent bodies in Shared are smaller than in 06.
- Decision: a two-step screen on desktop and phone; the concept shows a separate decision screen with a single confirm; this is the owner's two-step requirement.

### Not verified

- A real phone, iPhone 18 sizes, real safe-area insets (CSS only), Dynamic Type, screen readers, frame rate, rendered contrast of the labels and terminal colours.
- NO_COLOR as the shell variable (only `?nocolor` and `C` in the web prototype).
- The named list sheet with more than five projects (not reachable with the fixture data).

## What round 8 changed

- **Owner rule (verbatim, 2026-10-21): "I like the new concepts of codex but the it remove the project name from the new visual design that was usefull".** Every project hull shows its name on every screen: desktop, Replay, phone and terminal. The v2 images drop the names; this build keeps them. Project names rank first in the label budget.
- **Phone Overview (under 640 px; the phone route uses the same scene).** One composition: the focus missions (waiting first, then running) sit inside their real project's hull (Harbor), the Archeus star sits between them with an ARCHEUS label, other projects are small receded octahedra with their names, directional threads carry small arrowheads, orbit rings are off. Labels: focus missions and project names only. The waiting mission carries a filled 48 px Review button. Chips: one "All work" chip opens the full list. Headline 34 px serif, status line below it.
- **Phone sheets.** The detail sheet shows state, title, What, Why, "Core (fixture text)", "Open decision" (the decision page shows the action hash and plan version from fixtures) and Close. The conversation sheet has a grabber; General answers carry a "General" tag and the off "Promote to project memory" control.
- **Desktop label budget.** Far (whole space): project names, Archeus, and missions that need you or are running. Zoomed to a project: all of its missions. Hovered figures always show. The rest are counted in a "+N more missions" note. The core label sits below the star rays.
- **Typography.** UI and mission labels are sans; serif is the wordmark, the headlines and the Archeus name only.
- **Terminal, rebuilt on a character grid.** 120 x 40: ARCHEUS star, the Harbor box with its two focus missions (amber mission with its state and "[Enter] Open decision"; blue star mission with its chain Verifying, Codex, Verification, Results), "+1 more", dashed links to Notes and Lantern boxes with counts, a Why line, a key-hint bar, a tell line (not sent) and the SIMULATED line. 80 x 24: stacked project boxes, one row per mission. Mission, decision and Replay screens use the same boxes. Keys added: `?` help, `:` jump to a project, mission or replay, `/` filter, `L` plain-line mode (labelled lines, no boxes), `a` then `y` to approve in the decision screen (the confirm step is shown; nothing is approved). Every state has a glyph and a word; the output uses no colour.
- **Decision.** The plan page shows the action hash and plan version from the fixture; Approve opens the confirm box, which names the hash. Nothing is approved in the prototype.
- Service worker cache bumped to `archeus-v2-proto-8`. `check.mjs` updated for the General tag.

### Sizes and checks (round 8)

- Phone Overview, checked by eye and by label boxes at 360 x 800, 390 x 844, 393 x 852, 402 x 874, 430 x 932 and 440 x 956: no horizontal scroll, zero label overlaps with the bar or the chips, every visible control at least 48 px, project names present (Harbor, Notes, Lantern). Montage: `scratchpad/t123/r8-phone-sizes-montage.png`.
- Desktop Overview, label boxes: zero overlaps at 1280 x 720, 1440 x 900, 1600 x 900 and 1920 x 1080, project names included.
- Desktop Replay: zero overlaps at 1600 x 900 and 1920 x 1080. At 1280 x 720 and 1440 x 900 the verb labels "contains" and "executes" touch a node or each other. At phone widths the Replay verb labels overlap (six pairs at 390). Not fixed in round 8.
- iPhone 18 sizes remain unverified (see round 7). Safe-area insets are CSS-only.

### Apple HIG and design-audit, round 8

- Applied this round: 48 px targets on the phone, sheet grabber, solid sheet backgrounds, sans for UI text.
- design-audit: loaded, and its reduction filter and dimensions applied by hand to the round 8 screenshots. Its protocol asks to present a plan and wait for approval before changing anything; this round could not wait, so the phased-approval step was not run.
- typography skill: not run as a separate pass. The type scale is 34 px headline, 22 px label, 16 px body, 14 px minimum.

### Still weaker than the images

- Phone: no matte facet shading; the bodies are wireframes with a faint wash, not filled faces. The composition is still busier than phone-1.
- Terminal: no colour at all, while the concept uses amber and blue for states; the glyph and word carry the state. The tell line is not dimmed (the text block has one colour). The 80 x 24 layout has no Why line.
- Desktop: the default Overview is still busier than desktop-1-now-v2 (the hull fill is more visible, the core label sits near the rays). The Replay constellation has no hull around the mission, unlike replay-2.
- Decision: a plan page plus a confirm box, not a separate screen on the desktop. The phone decision is the same page.

## What round 7 changed

- **Phone (under 880 px) is one calm screen.** The Overview is a short headline, the constellation, and one bar at the bottom. The bottom navigation bar is gone: Places opens the list of screens from a button at the top. Only the two focus objects are labelled (the one that needs you and the live one); everything else is unlabelled and the scene is larger. Count chips above the bar ("3 projects", "5 more missions") open the full list in a sheet.
- **Sheets.** One tap on a figure opens a detail sheet (about 46 percent of the screen, with a grabber): state, title, what, why, and "Review plan" or "Open mission". The conversation opens as a sheet from the bar; the Start card and the General thread live there. The sheet's background is solid, so text does not show the scene through.
- **Safe areas.** `viewport-fit=cover`; top and bottom padding use `env(safe-area-inset-*)`, so the bar clears the home indicator and the header clears the Dynamic Island. The bar and Stop sit in the lower third.
- **Terminal (new route, `#/terminal`).** The overview, mission, decision and replay are drawn as monospaced text from the same fixture data, at 80 x 24 and 120 x 40. Keys: j/k or arrows move, Enter opens, r reviews, p opens the replay, t focuses the tell line, Esc goes back. The tell line says the text was not sent. The 80-column overview is stacked, one project per block.
- **Desktop.** Mission and record labels drop their kicker line (fewer, smaller labels); "New" sits on the title of a new object for six seconds. Replay rows are tighter, so the Reconcile row and the footer fit at 900 px height. Atlas's second mission moved. Default Overview has zero label overlaps at 1280 x 720, 1440 x 900, 1600 x 900 and 1920 x 1080.
- Phone first screen follows the Codex structure and the research ranking: status headline, one Needs-you card (one tap opens the detail sheet), count chips (projects, more missions, Replay), the bar and Stop in the lower third.
- Terminal keys follow the Codex proposal: j/k, Enter, r review, p replay, t tell, s stop (existing double-press), b back. Terminal text is ASCII only; no colour is needed to read a state.
- Measured label overlaps, label-box count (not a visual audit): default Overview zero at 1280 x 720, 1440 x 900, 1600 x 900 and 1920 x 1080. Demo chat flow zero at 1440 x 900, 1600 x 900 and 1920 x 1080; at 1280 x 720 two pairs (Archeus with the Codex label; Atlas with Search provenance).
- Service worker cache bumped to `archeus-v2-proto-7`.

### Phone sizes tested (Chromium, CSS px)

360 x 800, 390 x 844, 393 x 852, 402 x 874, 420 x 912, 430 x 932, 440 x 956. Measured on each: zero label overlaps with the bar or the count chips; no horizontal scroll; every visible button and link at least 44 px (the rule is 48 px in the CSS); the smallest text 14 px (label rule); body text in sheets 17 px.

Not verified: the iPhone 18 (not in the Apple device table in the reference pack; no verified size); the iPhone 17 and 17 Pro sizes (402 x 874) and the Air (420 x 912) are from the reference table, not measured on a device. Real safe-area insets are 0 in the desktop browser used here, so the Dynamic Island and home-indicator clearances are CSS-only and untested on hardware.

### Apple HIG rules (from the reference pack, read-only) and how they apply to this web prototype

Applied in CSS and layout:
- Safe areas: content clears the top and bottom system insets with `env(safe-area-inset-*)`; the bottom bar sits above the home indicator; the header sits below the Dynamic Island.
- Touch targets: 44 pt is the iOS floor; the CSS uses 48 px for every control on the phone (the owner's rule).
- Tab bar at most five items: the six-item bottom bar became a Places sheet.
- Sheets with a detent and a grabber: a detail sheet and a conversation sheet at about 46 percent, with a grabber and a close button; Escape closes them.
- Primary actions in the thumb zone: the bar and Stop are at the bottom.
- Body text 17 px in sheets (HIG default), label text 14 px minimum (the owner's rule; HIG's minimum is 11 pt).
- Reduce motion: the existing CSS and JS paths stop motion when the user prefers reduced motion.
- Materials: solid sheet backgrounds, no translucent sheet over the scene (the reduced-transparency gate is kept for the desktop panel).
- Semantic colour tokens (no raw colour in components); focus ring kept visible.

Not applied, and why:
- Dynamic Type: the page uses fixed px sizes with a 14 px floor; the browser's text zoom works, but true Dynamic Type is native-only.
- Haptics, Live Activities, Dynamic Island content (the status shown inside it): native-only; the prototype does not create a Live Activity.
- Liquid Glass chrome: the prototype uses flat dark surfaces, not the system glass material.
- SF Symbols: the icons are inline SVG (no system symbol font on the web).
- Native sheet detents and gestures: approximated with a 46 percent sheet and a close button; no drag-to-resize.
- Widgets and the iPad layouts: out of scope for a phone prototype.

## What round 6 changed

- Overview: the constellation fills the stage. The conversation floats low over it (the last lines, light tint), and the bar sits at the bottom edge with Tell and Stop. The conversation column is gone.
- Start card: a mission created from chat offers "Start and plan <title>? [Start] [Keep as mission]". Start plans it for review; Keep leaves it idle. The owner's answer makes this the intended behaviour; V1 does not do it yet.
- Creation cues: a new object grows in; its link is drawn in dashed; its label carries "New" for six seconds. No glow, rings or particles.
- Replay: the mission's own small constellation on the left (Archeus at the top, the mission node, execution triangle, verification and results) and the replay panel on the right with six rows (09:00 Intended, 09:12 Recorded, 09:18 Verified, 09:24 Uncertain, 09:25 Needs you, and a Reconcile row with Reconcile and Open evidence). The line "Not every external effect can be reversed." ends the panel.
- Phone (under 880 px): constellation above, the conversation above the bar, the bar and Stop above the navigation bar.
- Label placement: Harbor's missions moved so its label clears Fix date test; Atlas moved down and its missions re-spaced. Measured with a label-overlap count (see gaps).
- Satellite bodies: five small wireframes sit between the figures. Shared devices show a state word in colour (Connected, Recent, Future).
- The "ORCHESTRATES" verb sits lower on the link, clear of "Core connected".
- Service worker cache bumped to `archeus-v2-proto-6`.
- `check.mjs` covers the Start card, the Replay words and the chat feed styles.

## What round 5 changed

- Chat bar on Overview. Scripted replies (keyword routing, no model). Project-bound messages create objects that appear in the constellation as they are made: a project star (Atlas), a mission, an idea (an idle mission here), a plan with three steps (the mission waits for review).
- Anything that runs or changes a setting is a PROPOSED card. Approve opens the confirm box (Cancel is the default); only then does the page change.
- A question outside projects is answered in a General thread, marked "not project memory". "Promote to project memory" is off by default.
- Replay view (`#/replay/m-date`, also "Open replay" on a mission). Reconcile is a confirm box that changes nothing.
- Shared inspector: Content and Relations are row lists instead of fixture sentences.
- Label type scales with the scene size (floor 0.72).

## What round 4 changed

- Labels leave radially: a mission label from its project centre, a project label from Archeus, pushed out past the hull edge (a hull collision cost keeps the project label outside its hull).
- Four relaxation passes move any label that still touches another one outward along its radial (round 6: ten passes).
- Layout check: at a 1440 x 900 viewport the hub fills the stage.

## What round 3 changed

- Hub model: Archeus at the centre, each project a faceted hull around its missions, each mission a rotating polyhedron with a glyph inside. The hull has an inner mesh; a relation line runs from the hull to the core.
- State by shape and word, never colour alone: waiting is an amber diamond on the figure and "Needs you" on the label; running is a blue sparkle with a pulse and "Running"; done is a green disc with a tick; idle is a hollow slate ring.
- The lit chain (Archeus, project, mission, execution) is bright; live links carry a travelling pulse; the rest recede.
- The waiting mission carries an inline Review link on the scene (keyboard reachable). Review opens the plan approval screen.
- Phone (under 880 px): a compact hub, one bounded zoom step to a tapped star, and a slim review sheet. The rail becomes a bottom bar.
- Tokens: one block in `style.css` for colour, type and space. Data model (missions, projects, plans) is in `app.js`, separate from the drawing.

## How to open

- Serve the folder (see the first line). Screens switch from the left rail (desktop) or the bottom bar (under 880 px).
- Keyboard: Tab moves through rail items, the chat bar, projects, figure hit targets and the Review links. Enter on a project zooms; Enter on a mission opens it; Escape returns to whole space or closes the phone sheet.

## What is fake

- Every project, mission, plan, comment, device and count is a fixture in `app.js`, except what the chat creates during the session. Nothing reads Core, the API or a device, and a reload resets the chat.
- Chat replies are scripted. No model is called and nothing is sent to Core.
- Start (the Start card), Approve on a chat card, Tell, Stop, plan Approve, Request changes and Reject change this page only. Nothing is run, sent, spent or stopped.
- Replay is sample data. Reconcile and Open evidence change nothing.
- Consequence lines marked "fixture text" stand in for Core's own text.
- Every screen carries a "PROTOTYPE · fake data" label. The chat carries "Simulated".
- The real-versus-faked table (what V1 does today, per the T-149 truth check) and the owner answers are in `docs/design/ARCHEUS_V2_LIVING_SPACE.md`, round 4, sections 4 and 6.

## Screens

| Screen | Route | Reference |
|---|---|---|
| Overview (hub + chat) | `#/now`, `#/now/harbor` (zoomed), `#/now/chat` (focus the bar) | `02-now` composition; Codex `chat-1-desktop-now-chat` |
| Mission | `#/mission/m-date` | `03-mission`: chain, phase stepper, tabbed inspector |
| Replay | `#/replay/m-date` | Codex `replay-2-desktop-mission`; design doc round 4, section 3 |
| Shared | `#/shared` | `06-shared`: agents and devices as endpoints; tabbed inspector |
| Phone | `#/phone` | `10-phone-needs-you`: compact hub, Review, slim sheet. Codex `chat-3-phone-390` for the chat |
| Plan approval | `#/plan/m-search` | Design doc section 4.2 |

## Remaining gaps against the approved concepts (after round 8, see round 8 section)

Honest state. Checked by Playwright screenshots and label-box counts. Still weaker than the concepts:

- Desktop, demo flow at 1280 x 720: two label pairs touch (Archeus with the Codex label; Atlas with Search provenance). Default Overview is clean at all four desktop sizes; the demo flow is clean at 1440, 1600 and 1920.
- Desktop figures are still thinner and dimmer than 02 and 03; the satellites are five small wireframes.
- Phone: the scene is smaller than the concept in height; the Codex structure proposal (pending) and the iPhone 18 size (unverified) are not reflected yet.
- Terminal: plain text grid drawn by the page; the concept images use the same characters but a richer layout (boxes and columns); 80 x 24 uses a stacked list.
- Shared devices: cubes, state word in colour, no state dots.
- Not verified: a real phone, a screen reader, frame rate, rendered-pixel contrast (only the palette pairs in check.mjs), Dynamic Type, haptics.
- Service worker: network-first with a shell cache; bump `CACHE` in sw.js when the shell changes (now `archeus-v2-proto-7`).
- check.mjs checks files, syntax, manifest, icons, contrast pairs, font floor, Canvas 2D, devicePixelRatio, hidden-tab pause, reduced motion, the chat, Replay, phone and Terminal rules. It does not run the UI. Run it as `node clients/v2-prototype/check.mjs` through the shared test lock.
