Serve with py -m http.server 8000, then open http://127.0.0.1:8000 (open a terminal in this folder first; file:// does not work for the PWA).

# Archeus V2 prototype (fake data, simulated chat)

A clickable prototype of the V2 living space. Plain HTML, CSS and Canvas 2D. No framework, no build step, no npm, no web fonts, no CDN.

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

## Remaining gaps against the approved concepts (after round 6)

Honest state. Round 6 was checked by Playwright (Chromium) screenshots at 1440 x 900, 1600 x 900, 1920 x 1080, 1280 x 720 and 390 x 844, and compared by eye with the Codex images (`chat-1`, `replay-2`, `chat-3`) and with 02, 03, 06, 10 and 13. It is still weaker than them in these places:

- Figure density: the interior mesh and glyphs are thinner and dimmer than 02, 03 and the Codex images. Satellite bodies are five small wireframes, not a dense field.
- Label overlaps are scored, not perfect. Measured with a label-box count: at 1600 x 900 the default Overview is clean and the demo chat flow (Atlas, its mission, its idea, its plan) is clean. At 1440 x 900 the demo flow has one pair (Reading list export with Map relations). At 1280 x 720 the demo flow has six pairs (Archeus and Codex, Atlas with its missions, Index notes with the Atlas mission). The 1280 x 720 case is the weakest.
- Atlas sits at a fixed spot in the upper middle of the scene. At 1600 x 900 its hull still touches the top edge of the stage. At 1280 x 720 it is crowded.
- At 1600 x 900 the conversation lines can cover the Codex label (the plan line of the demo flow sits over it).
- Phone: the conversation sits above the bar and the constellation sits above that, but the scene is small (about 380 px tall) and the feed's lowest line overlaps a project label at the bottom edge. The phone Overview is busier than concept 10 and the Codex chat-3 image.
- Chat: the Start card's "Start" plans the mission for review; the Codex image shows a card that starts a run. The prototype keeps the planning step (the Start card is design, and V1 has no card yet).
- Replay: the mission constellation is smaller than the Codex image's and has the record nodes (Date test suite, Results, Verification) instead of the Codex-style Verification and Results only.
- Shared: devices are still cubes; the state colour is on the word, not a dot.
- Not verified: a real phone, a screen reader, a frame-rate budget, contrast on rendered pixels (only the palette pairs in `check.mjs` are checked).
- Reduced motion stops the rotation, the pulse, the grow-in and the camera tween; it draws the same layout.
- Service worker: network-first with a shell cache from install. Bump `CACHE` in `sw.js` when the shell changes (now `archeus-v2-proto-6`).
- `check.mjs` checks files, syntax, manifest and icons, contrast pairs (including the translucent chat bar), font floor, Canvas 2D only, devicePixelRatio, hidden-tab pause, reduced-motion hooks, and the round 5 and round 6 chat and Replay rules. It does not run the UI. Run it as `node clients/v2-prototype/check.mjs` through the shared test lock.
