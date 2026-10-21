Serve with py -m http.server 8000, then open http://127.0.0.1:8000 (open a terminal in this folder first; file:// does not work for the PWA).

# Archeus V2 prototype (fake data, simulated chat)

A clickable prototype of the V2 living space. Plain HTML, CSS and Canvas 2D. No framework, no build step, no npm, no web fonts, no CDN.

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

## Remaining gaps against the approved concepts (after round 7)

Honest state. Checked by Playwright screenshots and label-box counts. Still weaker than the concepts:

- Desktop, demo flow at 1280 x 720: two label pairs touch (Archeus with the Codex label; Atlas with Search provenance). Default Overview is clean at all four desktop sizes; the demo flow is clean at 1440, 1600 and 1920.
- Desktop figures are still thinner and dimmer than 02 and 03; the satellites are five small wireframes.
- Phone: the scene is smaller than the concept in height; the Codex structure proposal (pending) and the iPhone 18 size (unverified) are not reflected yet.
- Terminal: plain text grid drawn by the page; the concept images use the same characters but a richer layout (boxes and columns); 80 x 24 uses a stacked list.
- Shared devices: cubes, state word in colour, no state dots.
- Not verified: a real phone, a screen reader, frame rate, rendered-pixel contrast (only the palette pairs in check.mjs), Dynamic Type, haptics.
- Service worker: network-first with a shell cache; bump `CACHE` in sw.js when the shell changes (now `archeus-v2-proto-7`).
- check.mjs checks files, syntax, manifest, icons, contrast pairs, font floor, Canvas 2D, devicePixelRatio, hidden-tab pause, reduced motion, the chat, Replay, phone and Terminal rules. It does not run the UI. Run it as `node clients/v2-prototype/check.mjs` through the shared test lock.
