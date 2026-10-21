# Archeus V2 prototype (fake data)

Unzipped: open a terminal in this folder, run `py -m http.server 8000`, then open http://127.0.0.1:8000. file:// does not work for the PWA.

A clickable prototype of the V2 living space and the phone live remote. Plain HTML, CSS and vanilla JS. No framework, no build step, no npm.

## How to open

- Double-click `index.html`, or
- serve the folder with any static server, for example `py -3 -m http.server 8000` from this folder, then open `http://localhost:8000`.

The service worker and the install prompt need http(s). Opened from `file://` the page works, but no offline cache and no install.

Screens switch from the left tab (desktop) or the bottom bar (under 720 px). The phone screen is also a full-width layout at 390 px.

## What is fake

- Every project, mission, plan, comment, device and count is a fixture in `app.js`. Nothing reads Core, the API or a device.
- Tell, Create mission, Approve, Request changes, Reject and Stop only change this page. A new star from Tell or the mission form exists until the page is reloaded. Nothing is sent, approved or stopped.
- Approve, Request changes and Reject open a confirm box with Cancel as the default. The result is a message on the page saying nothing was recorded.
- Consequence lines marked "fixture text" stand in for Core's own consequence text.
- Every screen carries a "PROTOTYPE · fake data" label in the header.

## Screens and concept images

| Screen | Route | Concept / design reference |
|---|---|---|
| Now (a) | `#/now` | `docs/design/v2-concepts/02-now.png`; list mirror per LS-5 |
| Mission (b) | `#/mission/m-date` | `03-mission.png`; R3-12 six-phase list |
| Shared (c) | `#/shared` | `06-shared.png` (devices as endpoints, "Other people" as a future contract) |
| Phone (d) | `#/phone` | `10-phone-needs-you.png`; tap a star for one bounded zoom step and the slim review sheet |
| Start (e) | `#/start` | Design doc section 4.1 and R3-N1/N2 (no concept image exists) |
| Plan approval (f) | `#/plan/m-search` | Design doc section 4.2 and R3-N3/N4 (no concept image exists) |

Terminal concepts (13, T1 to T3) are not built here. They are text, not this screen set.

## Open items

- Not checked on a real phone, under real reduced-motion/transparency settings, or with a screen reader. Contrast is checked for the palette pairs only (`check.mjs`), not on rendered pixels.
- The phone review step scales the stage to 1.35x around the tapped star (400 ms). Reduced motion makes it instant. Owner answer Q3 says one bounded step; the exact scale is a judgement to review.
- Breath amplitude (about 6 percent over 6 s) and the event pulse are not tuned. The event pulse is not implemented.
- Per-task comments: the UI stores comments in memory and carries selected ones into the request-changes dialog. The planner contract (Q6, option A) is not built.
- Stale-plan handling (the Approve control re-reading when the plan changed elsewhere) is not implemented.
- Installability: the manifest references PNG icons 192 and 512 plus a maskable 512 (`icon-*.png`). The install prompt is not tested on a real device.
- Service worker is network-first with a shell cache from install. Bump `CACHE` in `sw.js` if the shell changes and you need an offline copy refreshed.
- `check.mjs` checks files, syntax, manifest, contrast pairs, font floor and key accessibility hooks. It does not run the UI. Run it as `node clients/v2-prototype/check.mjs` from the repo root, through the shared test lock.
