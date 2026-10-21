Serve with py -m http.server 8000, then open http://127.0.0.1:8000 (open a terminal in this folder first; file:// does not work for the PWA).

# Archeus V2 prototype (fake data, simulated chat)

A clickable prototype of the V2 living space. Plain HTML, CSS and Canvas 2D. No framework, no build step, no npm, no web fonts, no CDN.

## Round 10f desktop Overview fonts (2026-10-22): follow-up to 10e

Owner decision (font bake-off, D:ontbakeesults.md): no free face matched the concept serif (best mean IoU 0.47); serif is Libre Caslon Text, weight 500; sans is Source Sans 3 400 (chosen over Inter by shape IoU at width-solved sizes: 0.418 against 0.382 on 22 sans items). EB Garamond and Inter are removed from the client.

- Headline: 37.42 px, tracking +1.08 px (the bake-off gave +1.00 px; re-solved against the 1296 master: 455 px concept width matched to within 0.1 px). Ink height is about 2 px shorter than the concept's (the concept serif is taller).
- Per-element sizes solved by `tools/textfit_desktop.py caslon` (width against the concept ink; 11 px minimum on the frame, tracking where an item is clamped). Registration by `tools/textreg_desktop.py` (render ink box minus concept ink box).
- Other changes: wordmark tracking 2.2 px and weight 400 (V2 kept inside the rail overflow, which is now visible); nav band flush (no radius); Tell and Stop label padding; the midpoint between the star and the apex was not refilled (a dark spot showed, worse than the halo).
- Service worker cache archeus-v2-proto-d2 (fonts changed).

Measured (`metrics.py`, full resolution, unblurred, mean abs RGB 0 to 255 and % above 24; 1296 x 755, reduced motion, fonts awaited):

| region | 10e | 10f |
|---|---|---|
| art only, outside live boxes | 0.42 / 0.35 % | 0.34 / 0.26 % |
| text boxes | 29.7 / 24.4 % | 28.5 / 23.8 % |
| live marks | 19.4 / 19.4 % | 19.4 / 19.4 % |
| header | 13.8 / 14.0 % | 12.9 / 13.4 % |
| rail | 5.6 / 3.1 % | 5.5 / 3.0 % |
| chat and composer | 8.5 / 6.6 % | 7.9 / 6.3 % |
| full frame | 5.26 / 4.2 % | 5.02 / 4.0 % |

Headline box (172 to 642 x 66 to 122) mean abs: 33.96 (EB Garamond at 10e: 41.95). Search provenance label box: 43.9 (EB Garamond: 33.1), so the serif change is not better on every element; the title weight was the reason to keep 500 for the headline only and 400 for titles was not tested in this round.

Residuals (round 10f):
1. Serif glyph shape: Libre Caslon is heavier and wider than the concept's serif at the same ink height; the widths are matched by the solver, the heights are about 2 px short on the headline and 1 to 2 px on the titles. No free face matched (bake-off).
2. Search provenance title box is worse than with EB Garamond (43.9 against 33.1).
3. Star and apex: the refilled disc around the Fix date test star shows a slightly darker ring at 4x (crop: cx_halo_y.png in scratchpad d10d); the blue halo between the star and the apex is still faintly visible.
4. Tell and Stop: icon plus text ink 3 to 5 px narrower than the concept's (Stop 39 px against 48).
5. Sub-lines at 11 px (Captured, New, Early concepts.) and the card text still differ in width by 1 to 3 px.

Checks: `check.mjs` through the testlock (see the round 10f commit message and the final report). Overlap and clipping probes and the DPR 2 render were run on this state (see the final report).

## Round 10e desktop Overview (2026-10-22): hybrid, residuals listed

Owner rules applied: the concept's own sizes win on the desktop frame; frame text is at least 11 px (Apple HIG 11 pt), other views keep 14 px; tappable controls keep 44 pt hit areas without changing the visible shapes. Hybrid method unchanged: art (`art/desktop-now-base.webp`, built by `tools/art_desktop.py`) under live DOM text, live SVG marks and live SVG links.

What changed:
- Marks are live SVG shapes (`buildDeskMarks`, `updateDeskMarks`): amber diamond with glow (Search provenance), grey diamonds (Docs refresh, Offline capture), blue four-point star (Fix date test), ivory sparkle (Export backup, only its New word amber), the Codex triangle with its `</>` glyph and apex dot, blue Verification and Results dots. Colours come from the node state through `STATE`. The canvas no longer draws marks on the Now frame.
- Live links redrawn: Fix date test to the Codex apex, and the two Codex sides, because the art's copies are cleared under the marks. Their colour is the blue of the running state.
- Text sizes solved from the concept raster by `tools/textfit_desktop.py` (ink width and cap height, PIL). Registration of each text item against the concept (render ink box minus concept ink box) by `tools/textreg_desktop.py`; offsets are in `style.css` under "Round 10e registration".
- Chat: bubbles 276 x 34 and 335 x 34 at the concept's positions, filled #1E1927, label column 56 px, card 518 x 42 with hairline border, Start 87 x 30, Keep as mission 130 x 30, composer 690 x 44 with the paperclip and a 26 px round send button.
- Review button 99 x 31 at 354, 329 (measured on the master). Header: status 11 px, Tell and Stop 88 x 29 and 90 x 29 with the speech bubble and red square icons.
- Art: the masks round the star and the Codex apex are refilled from a ring (discs), so no blue halo is left under the marks except a faint tint between the star and the apex (residual 4).
- Service worker cache `archeus-v2-proto-d1` (distinct from the phone branch).

Measured (`metrics.py`, full resolution, unblurred, mean abs RGB 0 to 255 and % above 24; 1296 x 755 viewport, reduced motion, fonts awaited):

| region | round 10d | round 10e |
|---|---|---|
| art only (outside live boxes) | 0.85 / 0.70 % | 0.42 / 0.35 % |
| text boxes | 34.1 / 27.0 % | 29.7 / 24.4 % |
| live marks | 21.6 / 22.1 % | 19.4 / 19.4 % |
| header | 17.7 / 15.9 % | 13.8 / 14.0 % |
| rail | 6.2 / 3.5 % | 5.6 / 3.1 % |
| chat and composer | 13.4 / 8.3 % | 8.5 / 6.6 % |
| full frame | 6.85 / 4.9 % | 5.26 / 4.2 % |

Per-element register (render ink box minus concept ink box, master px): status dx -1, dy +1; NOW dx -2; headline dx 0, dy +2 before the offset; lede dx -4; ARCHEUS dx -3; Search provenance dx -5; Docs refresh dx -4; Fix date test dx -3, dy +9 before the offset; Verification and Results dy +12 before the offset; chat rows dx +3 before the padding fix; widths within 2 to 5 px where the solver could match them (see the table in tools/textfit_desktop.py output).

Residuals (each with a reason; crops in scratchpad d10d, `top_residual_blocks_r.png`):
1. Headline and serif titles (top 10 error blocks, all on the headline row y 72 and the Search provenance row): the concept's serif has a larger x-height and heavier stroke than EB Garamond 400. Weight 500 was tested and is worse (headline box 47.6 against 42.0), so the stroke is not a weight problem. Glyph match needs a different face or a glyph-level fit, which was not done.
2. Sub-lines at the 11 px minimum: Captured, New, Early concepts. are 1 to 6 % wider than the concept (the concept's sub-lines are smaller than the rule allows; the rule wins).
3. Marks: the Codex apex and the blue glow read a little larger than the concept's glow; the Fix date test star has a 1 px lower-left offset.
4. Faint blue halo between the Fix date test star and the Codex apex, under the live link (the art's glow, outside the refilled discs).
5. Export backup label ink was not found by the register probe (the sparkle and label sit on the mesh); visual check only.
6. Tell and Stop labels: the concept's text sits 2 to 4 px left of ours; the 88 x 29 and 90 x 29 boxes match.
7. Chat card text ("Start and plan Export backup?") is 1 to 3 px shifted and 0.5 % wider; the Keep as mission box matches to 1 px.
8. The Notes sub-line (two lines) is 11.5 px and reads a little wider than the concept.

Not verified in this round: the flicker itself (only the two lossless PNG frames and the 50 % alpha overlay were written: `alt_A_concept.png`, `alt_B_render.png`, `alpha_overlay_50.png`, in scratchpad d10d); the phone; motion (none, by brief); reduced motion beyond the render's `reduced_motion` context; `?nocolor` on the Now frame (the flag only affects the terminal colour; not changed here).

Checks: `check.mjs` (frame text min 11 px, other views 14 px) passes when run directly with node. The run through `testlock.py` was queued behind the two shared slots and was still waiting when this section was written. Overlap probe (label boxes, Chromium): zero overlaps at 1280 x 720, 1440 x 900, 1600 x 900 and 1920 x 1080. Clipping probe (scroll overflow of live text): no visible clipping; the flagged items are line-height overflow on the headline and labels, and the screen-reader label. Accessible names and tab order: checked with Chromium (all buttons and links named; the tab order runs Overview links, labels, Start, Keep as mission, composer, Send).

## Round 10d desktop Overview (2026-10-22): hybrid, PARTIAL

Method changed by the owner: the scene picture is the concept raster itself; everything live sits on top. The vector trace is tooling only (`tools/trace_desktop.py`, not shipped).

- Master: `D:\hub-concepts-codex4\desktop-1-now-v2.png`, 1296 x 729 px (not 1600 x 900; the 1.235x montages were enlarged). The frame is 1296 x 729 CSS px at DPR 1 and is scaled uniformly to the window (`--k`, `fitFrame`). The footer disclosure sits in a 26 px strip below the frame, so the 1:1 capture viewport is 1296 x 755.
- Base art: `art/desktop-now-base.webp` (lossless, 593 KB) and the 1296 x 729 PNG source (not shipped). Built by `tools/art_desktop.py` from the concept: glyph pixels of every live label, rail item, header control, chat row and composer box are removed by local-contrast masks inside measured boxes, then inpainted (Telea). Flat UI boxes (chat, header controls, rail column) are refilled from a quadratic fit of their surroundings or a constant (the rail). Mesh wires and the amber and blue links stay in the art. Regenerate with `py -I tools/art_desktop.py`.
- Live overlay: the rail (Now, Projects, Replay with the same icons and the amber leading strip), header status and Tell and Stop, the NOW kicker and the headline, the lede, the chat rows with the label column, the Start card and the composer are DOM, positioned from the concept. Labels are the existing `.lbl` nodes; the Review button sits in the Search provenance label. Marks are still canvas-drawn (`drawDeskMark`, `drawDeskExec`), not SVG; that is a known deviation from the brief.
- Fonts: EB Garamond (serif, headline, labels and lede, chosen over Cormorant Garamond by overlaying the concept headline) and Inter (sans), self-hosted under `fonts/` with OFL texts and sha256 (`fonts/README.md`). Scoped to `body.frame-now`, so other views keep their fonts.
- Desktop-only gates: the canvas no longer draws hulls, facets, links or the knot on the Now frame (the art has them); the sky canvas is hidden; the project hulls still run `ringHull` for the label anchor with a no-op context (`NO_DRAW`).
- Hidden on the frame, as an approved change: the project list in the rail (the Projects view keeps it), the example prompts and the all-missions list (both still in the DOM, not visible).
- Service worker cache bumped to `archeus-v2-proto-13`; art and fonts added to the shell list.

Measured (full resolution, unblurred, 1296 x 729, Chromium 1296 x 755 viewport, reduced motion, fonts awaited; `metrics.py`, mean abs RGB 0-255 and % of pixels above 24):
- art only (outside all live boxes): mean 0.85, 0.70 % above 24. Registration proof: the art sits where the concept is.
- text boxes: mean 33.7, 26.6 % above 24 (EB Garamond sizes and tracking are not yet matched glyph by glyph).
- live marks (canvas glyphs): mean 21.6, 22.1 % above 24 (the concept glyphs are not replicated).
- header: mean 16.3, 14.8 %.
- rail: mean 6.0, 3.3 %.
- chat and composer: mean 13.4, 8.3 %.
- full frame: mean 6.8, 4.9 %.

Residuals (honest, numbered):
1. Text glyph shapes and widths: the serif labels run within a few px of the concept but are not glyph-matched; the headline is about 4 px narrower at the right.
2. Marks are canvas glyphs, not the concept's shapes (diamonds, the four-point star and sparkle, the code glyph in the triangle).
3. Chat bubble fill and the Start card border differ in tone and padding.
4. Review button: 99 x 31 px at the concept's position (the owner's 122 x 36 figure is from the 1.235x montage; 99 x 31 is the master measurement).
5. The rail band and icons are close, not matched glyph by glyph.
6. Lightly smudged areas under the Fix date test star and the Codex apex (the art removed live glyphs there); the live star and apex cover most of them.

Not verified in this round: other widths (1280, 1440, 1600, 1920) for overlap, the flicker and alternation images, high DPR, the phone.

## Round 10c desktop Overview (2026-10-21): PARTIAL, 5 loop iterations

Status: PARTIAL. The brief asks for at least 8 saved iterations and a stop only at zero visible differences or 15 iterations. This round ran 5 iterations, then stopped to close the round with the width checks and the deliverables. Remaining differences are listed below with numbers. Only the desktop Overview (Now) was worked on. Phone, Replay, terminal, Mission and Shared are unchanged in this round.

What was traced (from desktop-1-now-v2.png, 1296 x 729, read from a labelled grid): the constellation bounds (x 190 to 1212, y 80 to 516 in reference px), the hull outlines (Archeus 10 vertices, Notes 8, Ideas 5), the mission and Codex marks, the chat rows and the bar. The concept's constellation spans about 88 % of the stage width (from about 15 % to 93 % of the page), so the scene fills 88 % of the stage width.

Layout (desktop only, `nowScene`, app.js):
- `DESK_BOX` = { x0 190, x1 1212, y0 80, y1 516 }; `DESK_FILL` = 0.88 of the stage width; `DESK_SCENE_H` = 0.74 of the stage height; `DESK_TOP` = 0.07. The scene height is also capped at the stage height minus a chat reserve (230 px at stage height 620 or less, 240 px above that), so the transcript never sits on the Codex triangle.
- Marks in reference px: Search provenance (330, 298), Docs refresh (368, 408), Fix date test (826, 344), Codex apex (871, 416), Verification (806, 488), Results (925, 488), Offline capture (1034, 175), Export backup (1040, 230). Core (640, 316).
- Hulls in reference px: Archeus 10 vertices as in `CONCEPT_LAYOUT.desktop`, Notes 8, Ideas 5.
- Label anchors (`sc.labelFix`): Notes at (1172, 112) with a two-line sub; Ideas at (1208, 427); Archeus label hidden (the star's ARCHEUS word is the name); Codex label below the apex; Verification and Results to the right of their dots, on the dot row.

Drawing (desktop only, all gated by `sc.desk` or `sc.knot` or `p.desk`):
- Star: `drawKnot`, 46 chords and spokes of fine ivory threads, a small bright centre. The phone keeps the old star (`drawCore` without the flag).
- Hulls: `deskFacetsFor`, 22 interior points, about 66 thin facet lines in three opacity tiers (0.5 / 0.3 / 0.16). No wedge fills on desktop.
- Marks: `drawDeskMark`, filled amber diamond for Search provenance, blue four-point star for Fix date test, filled lilac diamond for done and idle, amber sparkle for "New" (Export backup).
- Codex: `drawDeskExec`, blue triangle with the code glyph; apex dot and the Verification and Results dots form the base corners.

Chrome and CSS (style.css, one block at the end, `@media (min-width: 881px)`): grey fixture label in the rail, the top-bar pill hidden on desktop, Tell with a bubble icon and Stop with a square icon, the amber bar on the active rail item, More folded away, the headline block over the scene, the simulated note as a grey footer (moved out of the headline block in index.html), serif label titles, chat rows with a label column, the Start card on one line (`.card-body`), the chat bar at 850 px.

Similarity (`sim2.py`, both images to 160 px wide, blurred; lower lum MAD is closer; amber and blue MAD on the same scale):
- i1: lum 8.04, amber 0.69, blue 3.06, edge overlap 49.2 %
- i2: lum 7.83, amber 0.69, blue 3.07, edge overlap 50.6 %
- i3: lum 7.90 (after the Notes anchor fix), amber 0.69, blue 3.06, edge 51.0 %
- i4: lum 7.61, amber 0.64, blue 2.95, edge 52.9 % (constellation span fixed)
- i5: lum 7.64, amber 0.64, blue 2.94, edge 53.0 % (denser facets)
- i6 to i7: lum 7.64 to 7.67 (chat reserve, label fixes); the luminance metric barely moves after i4. It does not separate the iterations well; the judgement is by eye on the montages.

Label overlap probe (DOM boxes of visible labels, Chromium, desktop Overview): zero overlaps at 1280 x 720, 1440 x 900, 1600 x 900 and 1920 x 1080.

Checks: check.mjs through the testlock (see the round 10c commit). Service worker cache bumped to `archeus-v2-proto-12`.

Remaining differences (honest, numbered, 1600 x 900 unless stated):
1. Hull shape: the Archeus hull is a smoother polygon than the concept; the concept's facet web reads as more lines and a crisper outline. Facet count is about 66 against about 40 visible in the concept, so density is higher but the outline is less articulated.
2. Star: the knot is smaller and less crisp than the concept's (concept radius about 75 reference px, prototype about 60).
3. Concept's faint amber dashed link from Search provenance to Docs refresh is not drawn.
4. Export backup label sits below its node (to avoid the Offline capture label at small sizes); the concept places it to the right of the sparkle.
5. Sub-lines of Notes and Ideas use the prototype's sans; concept line breaks at "Research and capture / evolving context." match only in the wrap, not the width.
6. At 1280 x 720 the scene is smaller than at 1600 x 900 (the chat reserve takes height); not measured as a percentage.
7. Chat row heights and bubble padding were not measured against the concept's rows.
8. Type: label titles use the serif (concept look). This departs from the round 8 rule that labels are sans; recorded so the owner can choose.
9. Review button is 36 px tall, the concept's is about 30 px.
10. Stop and Tell icons are CSS-drawn (no SVG data URI, because check.mjs forbids the xmlns string in style.css); the concept's icons are slightly rounder.

Not verified: a real high-DPI display (renders at DPR 1 only), reduced motion and tab-hidden states on the new scene (the facets and knot are static and read the same), the phone sizes (only the shared markup and the Start card wrapper change there; the Start card wrapper is display block on the phone).

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
