Serve with py -m http.server 8000, then open http://127.0.0.1:8000 (open a terminal in this folder first; file:// does not work for the PWA).

# Archeus V2 prototype (fake data, simulated chat)

A clickable prototype of the V2 living space. Plain HTML, CSS and Canvas 2D. No framework, no build step, no npm, no web fonts, no CDN.

## What round 5 changed

- Chat bar on Overview, under the constellation, with a conversation column beside it. The Start screen and its form are removed; Tell opens the bar (`#/now/chat`).
- Scripted replies (keyword routing, no model). Project-bound messages create objects that appear in the constellation as they are made: a project star (Atlas), a mission, an idea (an idle mission in this prototype), a plan with three steps (the mission waits for review).
- Anything that runs or changes a setting is a PROPOSED card. Approve opens the confirm box (Cancel is the default); only then does the page change.
- A question outside projects is answered in a separate General thread, marked "not project memory". "Promote to project memory" is off by default.
- A visible tag says the chat is simulated.
- Replay view (`#/replay/m-date`, also "Open replay" on a mission): a forensic timeline with Intended, Authorized, Recorded, May have taken effect, Uncertain and Suspended, each with a shape and a word. Sample data is the 09:00 to 09:25 example from the strategy report. Reconcile and Restore are confirm boxes that change nothing.
- Shared inspector: Content and Relations are row lists instead of fixture sentences.
- Lit bodies carry a small vertex glow; the sky has more points.
- Label type scales with the scene size (floor 0.72), so 1280 x 720 keeps the bar in view.
- Creation animation: a new object grows in over 800 ms and its label fades in; reduced motion shows it at once.
- Service worker cache bumped to `archeus-v2-proto-5`.
- `check.mjs` covers the Start removal, the simulated tag, the translucent bar contrast, the General and promote controls, the approval-by-confirm path and the Replay states.

## What round 4 changed

- Labels leave radially: a mission label from its project centre, a project label from Archeus, pushed out past the hull edge (a hull collision cost keeps the project label outside its hull).
- Four relaxation passes move any label that still touches another one outward along its radial.
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
- Approve on a chat card, Tell, Stop, plan Approve, Request changes and Reject change this page only. Nothing is run, sent, spent or stopped. Approve and Reject open a confirm box with Cancel as the default.
- Replay is sample data. Reconcile and Restore change nothing.
- Consequence lines marked "fixture text" stand in for Core's own text.
- Every screen carries a "PROTOTYPE · fake data" label. The chat carries "Simulated".
- The real-versus-faked table (what V1 does today, per the T-149 truth check) is in `docs/design/ARCHEUS_V2_LIVING_SPACE.md`, round 4, section 4.

## Screens

| Screen | Route | Reference |
|---|---|---|
| Overview (hub + chat) | `#/now`, `#/now/harbor` (zoomed), `#/now/chat` (focus the bar) | `02-now` composition; hub images for the hull structure |
| Mission | `#/mission/m-date` | `03-mission`: chain, phase stepper, tabbed inspector |
| Replay | `#/replay/m-date` | Design doc round 4, section 3; the mission panel style of 03 |
| Shared | `#/shared` | `06-shared`: agents and devices as endpoints; tabbed inspector |
| Phone | `#/phone` | `10-phone-needs-you`: compact hub, Review, slim sheet |
| Plan approval | `#/plan/m-search` | Design doc section 4.2 |

## Remaining gaps against the approved concepts (after round 5)

Honest state. Round 5 was checked by screenshots at 1440 x 900, 1920 x 1080, 1280 x 720 and 390 x 844 (Playwright, Chromium), and compared by eye with 02, 03, 06, 13 and the hub concepts. It is still weaker than the concepts in these places:

- Figure density: the interior mesh and glyphs are still thinner and dimmer than 02 and 03. The vertex glow is on lit bodies only. No extra facets were added.
- Ambient mesh: more starfield points, but no satellite bodies between the figures yet.
- Label placement is scored, not perfect. At 1440 x 900 with Overview's default content the labels are clean. With Atlas and three of its missions, one label pair still touches ("Search provenance" and "Check sources"). At 1280 x 720 the labels of Map relations and Reading list export can touch, and the Harbor project label sits over its figures. The labels are smaller there.
- Atlas, the project the chat creates, is placed at a fixed spot near the top of the scene. Its hull is cut by the top edge of the stage. The spot was picked by a label-overlap count, not by a layout pass.
- Mission view: the "ORCHESTRATES" verb sits on the "Core connected" label.
- Mission inspector: the tabs (Overview, Activity, Plan) keep round 3 content; the concept's full panel is only partly matched.
- Shared: Content and Relations are row lists. The device bodies are still cubes with no state dots, so they do not match 06's device boxes.
- Phone: the Overview on a 390 px screen is busier than 10 and sits above a bar that is reached by scrolling. The Replay on the phone is a list.
- Replay: a timeline, not a constellation. It has no 3D figure and no hull; it follows the 03 panel style only.
- Chat: scripted and simulated. No streaming, no real latency, no Core, no model. The creation timing is the prototype's, not V1's.
- Not verified: a real phone, a screen reader, a frame-rate budget, contrast on rendered pixels (only the palette pairs in `check.mjs` are checked).
- Reduced motion stops the rotation, the pulse, the grow-in and the camera tween; it draws the same layout.
- Service worker: network-first with a shell cache from install. Bump `CACHE` in `sw.js` when the shell changes (now `archeus-v2-proto-5`).
- `check.mjs` checks files, syntax, manifest and icons, contrast pairs (including the translucent chat bar), font floor, Canvas 2D only, devicePixelRatio, hidden-tab pause, reduced-motion hooks, and the round 5 chat and Replay rules. It does not run the UI. Run it as `node clients/v2-prototype/check.mjs` through the shared test lock.
