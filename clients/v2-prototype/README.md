Serve with py -m http.server 8000, then open http://127.0.0.1:8000 (open a terminal in this folder first; file:// does not work for the PWA).

# Archeus V2 prototype (fake data, simulated chat)

A clickable prototype of the V2 living space. Plain HTML, CSS and Canvas 2D. No framework, no build step, no npm, no web fonts, no CDN.

## Round 10c replay (partial, 2026-10-21): desktop and phone form

Status: PARTIAL. Replay only. Traced from replay-2-desktop-v2.png. The brief names 1600 x 900, but the file is 1440 x 810 (same 16:9 frame); the loop rendered at 1440 x 810 and the montages are in the scratch folder.

Done: the constellation is drawn in the concept's pixels (`RC_FRAME` and the `RC` table in app.js), scaled uniformly into the stage (SVG), with labels as HTML at their own px size. Verb labels (orchestrates, executes, verifies, produces) sit at measured anchors. The six rows follow the concept row design (time column, mark, title, description, tag chip) with the Reconcile row (dashed, Operator tag, Reconcile and Open evidence) and the footer line. A faint hull surrounds the mission node, as the brief asks. The phone form (under 881 px) stacks the mini constellation above the rows; Back is a 48 px control in the panel head. No motion: the replay block has no animation loop (check.mjs asserts it).

Label overlap probe (label boxes, Chromium): zero overlaps at 1280 x 720, 1440 x 810, 1440 x 900, 1600 x 900, 1920 x 1080 and the six phone widths 360, 390, 393, 402, 430, 440. The mission and Codex labels are single blocks now, which fixed the stacked-label touches. The 'orchestrates' and 'verifies' touches of the earlier prototype are gone at 1600 x 900.

Layout table: `RC_FRAME` (x 192..779, y 40..800 of the concept; the phone uses the same frame with a 28 px top pad), `RC` (star, mission, Codex triangle, Verification, Results, verb anchors), `RC_LINKS` (link ends and heads). Row tokens are local `--rp-*` in style.css, so the shell tokens are unchanged.

Similarity (sim2.py, 160 px wide, luminance MAD / edge overlap): i1 6.45 / 67.2 %, i2 7.68 / 58.5 %, i3 7.21 / 62.4 %, i4 7.09 / 62.4 %, i6 7.20 / 62.0 %, i7 7.21 / 62.0 %. These numbers do not trend down. The metric is dominated by the dark background and the panel fill, and it does not register the star, label or link changes. It is not a usable target here; the judgement was by eye on the montages.

Differences left (numbered):
1. Star: the concept has crisp bright spikes over a tight core; ours is a soft glow with a few long rays.
2. Scale: the stage is about 515 px wide at 1440 x 810, against 587 px in the concept, because the shared rail is 240 px against 192 px in the concept.
3. Verification and Results are the shared ICO and OCT projections with simple glyphs; the concept's polyhedra are denser.
4. Shell, not replay (shared, left alone): rail items differ (concept: Overview, Missions, Ideas, Projects, Control; ours: Now, Projects, Replay, More), the PROTOTYPE pill sits top left, and the page background is #070A10 where the concept is a plum-black gradient.
5. Typeface: the system serif stands in for the concept's serif. Row title and sub positions are within 2 to 4 px; the timeline gradient is approximated.
6. Hull: the brief asks for a faint hull around the mission node; the target concept itself shows only a dot.
7. Desktop has no Back control (the concept has none); the rail reaches Overview.
8. Phone: only 402 x 874 was viewed by eye. The other five widths were checked by the probe only.

Not verified: real touch, screen readers, Dynamic Type, the Windows system serif against the concept's face.

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
