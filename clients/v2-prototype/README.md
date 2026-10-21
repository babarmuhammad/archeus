# Archeus V2 prototype (fake data)

Unzipped: open a terminal in this folder, run `py -m http.server 8000`, then open http://127.0.0.1:8000. file:// does not work for the PWA.

A clickable prototype of the V2 living space: Archeus at the centre, projects as constellations, missions as stars, and the live chains lit. Plain HTML, CSS and Canvas 2D. No framework, no build step, no npm, no web fonts.

## What changed in this version

- Now is a hub. Archeus sits at the centre. Each project is a constellation around it, and each mission is a star linked to its project.
- A chain Archeus, project, mission glows when the mission is live (needs you, or running). A running mission also has a flowing pulse along its links. Done and idle missions and their links recede. Projects with nothing live stay calm.
- Hover or focus a star or a project: its chain lights up and a small card shows the facts. Click a project: the view zooms gently into its constellation, and "Whole space" returns. Click a mission: its Mission screen opens.
- Every state has a shape and a word, never colour alone: waiting is an amber diamond with a dashed ring, running is a blue sparkle with a pulse, done is a green disc with a tick, idle is a hollow slate ring, execution is an ivory triangle, devices are rectangles (dashed when a future contract).
- Mission, Shared and Phone use the same renderer and the same style. The phone keeps the one bounded zoom step to a tapped star and the slim review sheet.
- Visual pass: deep ink base, ivory thread, one palette with muted project hues (teal, rose, lilac). Serif display (Iowan Old Style, Palatino, Georgia) with a system sans for UI and a mono face only for branch names. Soft glow on live work, a subtle starfield with parallax, an edge vignette for depth.
- Motion: camera eases with a 60 fps loop that runs only while something moves or work is running. The loop pauses when the tab is hidden. Reduced motion gives instant camera moves and no pulses or breathing.

## How to open

- Serve the folder (see the first line), or double-click `index.html` to see the page without the PWA.
- Screens switch from the left tab (desktop) or the bottom bar (under 720 px).

## What is fake

- Every project, mission, plan, comment, device and count is a fixture in `app.js`. Nothing reads Core, the API or a device.
- Tell, Create mission, Approve, Request changes, Reject and Stop only change this page. A new star from Tell or the mission form lasts until reload. Nothing is sent, approved or stopped.
- Approve, Request changes and Reject open a confirm box with Cancel as the default. The result is a message saying nothing was recorded.
- Consequence lines marked "fixture text" stand in for Core's own text.
- Every screen carries a "PROTOTYPE · fake data" label in the header.

## Screens and references

| Screen | Route | Reference |
|---|---|---|
| Now hub (a) | `#/now` | `docs/design/v2-concepts/02-now.png` for the composition; owner request for the hub model (Archeus centre, projects as constellations, live chains lit) |
| Mission (b) | `#/mission/m-date` | `03-mission.png`; chain Archeus, project, mission, execution; six phases as a list |
| Shared (c) | `#/shared` | `06-shared.png`; devices as endpoints, "Other people" as a future contract |
| Phone (d) | `#/phone` | `10-phone-needs-you.png`; tap a star for one bounded zoom step and the review sheet |
| Start (e) | `#/start` | Design doc section 4.1 (Tell first, project form second) |
| Plan approval (f) | `#/plan/m-search` | Design doc section 4.2; comments reach the planner only through request changes |

Terminal concepts (13, T1 to T3) are not built here.

## Open items

- Not verified on a real phone, with a screen reader, or on a real frame-rate budget. Contrast is checked for the palette pairs in `check.mjs`, not on rendered pixels.
- Screenshots from the capture tool were washed out, so the visual judgement used computed styles plus side-by-side screenshots. Compare on a real display.
- Labels can still crowd when many missions are added on Now; the layout is fixed, not auto-placed.
- The phone zoom uses a scale of 1.35 around the tapped star (400 ms). Owner answer Q3 says one bounded step; the scale is a judgement to review.
- Breath (about 6 percent over 6 s) and the pulse are not tuned. The event pulse is not implemented.
- Per-task comments are stored in memory and carried into request changes. The planner side (Q6, option A) is not built.
- Stale-plan handling (Approve re-reading when the plan changed elsewhere) is not implemented.
- Keyboard: Tab moves through projects and missions on Now; Enter on a project zooms, Enter on a mission opens it; Escape returns to whole space or closes the sheet.
- Service worker is network-first with a shell cache from install. Bump `CACHE` in `sw.js` when the shell changes.
- `check.mjs` checks files, syntax, manifest and icons, contrast pairs, font floor, Canvas 2D only, devicePixelRatio, hidden-tab pause and reduced-motion hooks. It does not run the UI. Run it as `node clients/v2-prototype/check.mjs` through the shared test lock.
