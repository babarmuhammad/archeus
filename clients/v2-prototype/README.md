Serve with py -m http.server 8000, then open http://127.0.0.1:8000 (open a terminal in this folder first; file:// does not work for the PWA).

# Archeus V2 prototype (fake data)

A clickable prototype of the V2 living space. Plain HTML, CSS and Canvas 2D. No framework, no build step, no npm, no web fonts, no CDN.

## What this round changed (round 3)

- Hub model, as the owner set it: Archeus at the centre, each project a faceted hull around its missions, each mission a rotating polyhedron with a glyph inside (search, terminal, check, document, chart, code). The hull has an inner mesh; a relation line runs from the hull to the core.
- State by shape and word, never colour alone: waiting is an amber diamond on the figure and "Needs you" on the label; running is a blue sparkle with a pulse and "Running"; done is a green disc with a tick; idle is a hollow slate ring.
- The lit chain (Archeus, project, mission, execution) is bright; live links carry a travelling pulse; the rest recede and stay faint.
- The waiting mission carries an inline Review link on the scene (keyboard reachable). Review opens the plan approval screen.
- Left rail: Overview, Missions, Shared, Phone, Start, Plan, and a PROJECTS list with coloured dots and counts. Hover or focus highlights a hull; click zooms the view to it, and Whole space returns.
- Top bar: "Not stopped · accepts new work" status, Tell and Stop.
- Headline: serif, 56 px at desktop width, with kicker labels (OVERVIEW, MISSION, SHARED SPACE, PROJECT, AGENT, EXECUTION, RECORD, DEVICE).
- Mission: the chain Archeus, project, mission, execution plus its records, with relation verbs on the links (orchestrates, contains, executes, uses, produces, verifies). The inspector has a phase stepper and three tabs (Overview, Activity, Plan).
- Shared: agents (Planner, Codex) and devices (This desktop, Paired phone) as endpoints, "Other people" as a dashed future contract. The inspector has three tabs (Overview, Content, Relations).
- Phone (under 880 px): a compact hub with Archeus and the two missions that need you most, no label collisions in the checked layouts, one bounded zoom step to a tapped star, and a slim review sheet. The rail becomes a bottom bar.
- Tokens: one block in `style.css` for colour, type and space. Data model (missions, projects, plans) is in `app.js` and separate from the drawing (scene builders return plain data; the stage draws it).

## How to open

- Serve the folder (see the first line). Screens switch from the left rail (desktop) or the bottom bar (under 880 px).
- Keyboard: Tab moves through rail items, projects, figure hit targets and the Review links. Enter on a project zooms; Enter on a mission opens it; Escape returns to whole space or closes the phone sheet.

## What is fake

- Every project, mission, plan, comment, device and count is a fixture in `app.js`. Nothing reads Core, the API or a device.
- Tell, Create mission, Approve, Request changes, Reject and Stop only change this page. Nothing is sent, approved or stopped.
- Approve, Request changes and Reject open a confirm box with Cancel as the default.
- Consequence lines marked "fixture text" stand in for Core's own text.
- Every screen carries a "PROTOTYPE · fake data" label in the top bar.

## Screens

| Screen | Route | Reference |
|---|---|---|
| Overview (hub) | `#/now`, `#/now/harbor` (zoomed) | `02-now` composition; hub images from the coordinator (`hub-1`, `hub-2`) for the project hull structure |
| Mission | `#/mission/m-date` | `03-mission`: chain, records, phase stepper, tabbed inspector |
| Shared | `#/shared` | `06-shared`: agents and devices as endpoints; tabbed inspector |
| Phone | `#/phone` | `10-phone-needs-you`: compact hub, Review, slim sheet |
| Start | `#/start` | Design doc section 4.1 |
| Plan approval | `#/plan/m-search` | Design doc section 4.2 |

## Remaining gaps against the approved concepts (round 3)

Honest state after round 3. Not run to the owner's full 8-round budget: this round rebuilt the renderer and checked Now, Mission, Shared and Phone in a 1440 emulation and a 390 px iframe.

- Figure detail is still lighter than 02 and 03: the interior mesh and the glyphs read at desktop size but are thinner and dimmer than the approved concept. Vertex dots and facet density need one more pass.
- The ambient mesh is restrained but sparser than 02. Satellite nodes between the figures are not yet drawn as separate small bodies.
- Label collisions are scored, not perfect: in the zoomed project view and in the mission chain, a label can sit close to a hull edge or a link. Verified on screenshots only at the emulated sizes.
- The hover card is placed away from the core but not tested against every zoom level.
- The mission inspector and the shared inspector follow the concept's tab structure, but the Content and Relations tabs carry fixture text, not designed panels as in 03 and 06.
- Phone: the review sheet is slim and text-first; the concept's translucency is only applied where the text contrast passes (prefers-reduced-transparency gate in CSS).
- Not verified on a real phone, a screen reader, or a real frame-rate budget. Contrast is checked for the palette pairs in `check.mjs`, not on rendered pixels.
- Reduced motion stops the rotation, the pulse and the camera tween; it draws the same layout.
- Service worker: network-first with a shell cache from install. Bump `CACHE` in `sw.js` when the shell changes (now `archeus-v2-proto-3`).
- `check.mjs` checks files, syntax, manifest and icons, contrast pairs, font floor, Canvas 2D only, devicePixelRatio, hidden-tab pause and reduced-motion hooks. It does not run the UI. Run it as `node clients/v2-prototype/check.mjs` through the shared test lock.
