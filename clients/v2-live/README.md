# V2 Live

A prototype of the Archeus V2 app that runs entirely on a fixture simulation: no Core, no network, no build step. Every screen says SIMULATED. Audience: internal review. It is the reference for look, layout, behaviour and wording when the real V2 UI is built (`SPEC.md` is the acceptance checklist).

## Run it

- Windows: double-click `start.cmd` (serves this folder on `http://127.0.0.1:8000` with `py -m http.server` or `python -m http.server`, then opens the browser). Close the server window to stop.
- Any OS: `python -m http.server 8000 --bind 127.0.0.1` in this folder, open `http://127.0.0.1:8000/`.
- It must be served over http, not opened as a file (ES modules).

## URL options

Options go in the query string, for example `index.html?theme=light&lang=it&sim=paused#/map`. The URL wins over what the app stored and is not stored itself.

| Option | Values | Effect |
|---|---|---|
| `theme` | `dark`, `light`, `dark-hc`, `light-hc`, `system`, `forced` | the look (`forced` simulates Windows forced colours) |
| `device` | `auto`, `phone`, `tablet`, `desktop`, `terminal`, `all` | the preview frame |
| `motion` | `system`, `full`, `reduced` | `reduced` is Quiet: the core mark is still |
| `lang` | `en`, `it` | English or Italian |
| `notes` | `on`, `off` | the dashed "Decision A10" notes that name the owner decision behind a choice |
| `sim` | `paused` | do not start the clock (default: plays at x1) |
| `speed` | `0.5`, `1`, `2`, `4`, `8` | clock speed |
| `advance` | seconds | move the simulated clock forward before the first draw |
| `seed` | number | another scripted story; the same seed gives the same story |
| `embed` | `1` | used by All devices: the page shares its parent's simulation |

## Routes

`#/now`, `#/work`, `#/attention`, `#/map`, `#/replay/<mission>`, `#/chat`, `#/security`, `#/health`, `#/usage`, `#/accounts`, `#/extensions`, `#/settings`, `#/more` (phone menu), `#/terminal`. A thing opens in a details sheet at `#/<route>/<id>`: missions `m-`, tasks `t-`, executions `x-`, plans `p-`, approvals `a-`, verifications `v-`, ideas `i-`, knowledge `k-`, projects `prj-`, accounts `acc-`, hooks `h-`, MCP servers `mcp-`, agents `ag-`. Examples: `#/work/m-date`, `#/attention/a-1`, `#/replay/m-date`.

## Devices

The toolbar's Device button picks Auto (fills the window), Phone 390, Tablet 820, Desktop 1440, Terminal (a text-mode view of the same state), or All devices: four live panes side by side, each laid out at its own real width, all driven by one simulation (act in one pane and the others change). Wide frames are scaled down to fit the window, which the note under the toolbar says.

## Simulation controls

Toolbar, Sim button (and Settings, Simulation): Play or Pause, speed x0.5 to x8, Trigger an approval, Inject a failure, Break the harness (trips the spawn breaker), Go offline or Reconnect, Reset. One real second is ten simulated seconds at x1. Pause all, Resume all and Emergency stop are on Now and in Settings; the emergency stop asks first, blocks new dispatch until re-armed (also possible while nothing runs) and Re-arm asks again.

## Keyboard

`?` lists the keys. `j` and `k` move through list rows and cards, Enter acts on the focused row or card, Space opens a row, Esc closes the help, a menu, an ask-first question or the details sheet. Focus order: toolbar, navigation, page, chat bar, bottom bar, then the details sheet (it takes focus when it opens and gives it back). The terminal view has its own keys (`?` there). The chat bar takes `/` for the 34 slash commands (English names, Italian aliases).

## Tests and probes

Run from the repository root; the repo's shared lock keeps heavy runs from overlapping.

| What | Command |
|---|---|
| unit tests (sim, spine, terminal, chat, replay, map) | `node --test clients/v2-live/test/*.test.mjs clients/v2-live/js/constellation/*.test.mjs` |
| layout probe: every route and overlay, 14 viewports, dark and light, overlap, clipping, targets, contrast, console errors, the one-animation rule | `py tools\v2_live_layout_probe.py` (`--lang it`, `--routes now,map`, `--viewports 390x844`) |
| map probe | `py tools\v2_livemap_probe.py` |
| design kit probe | `py tools\v2_live_design_probe.py` |
| All devices hit-test | `py tools\v2_live_alldevices_probe.py` |
| functional runs | `py tools\v2_live_s3_functional.py`, `v2_live_s4_functional.py`, `v2_live_tui_check.py`, `v2_live_s6_functional.py` |
| package | `py tools\v2_live_package.py` writes `Archeus-V2-Live.zip` (this folder without tests, `start.cmd`, `README-FIRST.txt`) |

## Files

`index.html`, `css/` (tokens, app, areas, chat, tui), `js/` (shell `app.js`, views, inspectors, areas, chat, Replay, keyboard, terminal view in `js/tui/`, map in `js/constellation/`), `sim.js` (the simulation, no DOM), `chat-engine.js` and `slash.js` (the one chat and command brain), `spine-model.js`, `core-words.js`, `replay-model.js`, `term.js`. `SPEC.md` is the feature inventory with status words BUILT, DESIGNED, PROTOTYPED and SIMULATED. `IT-REVIEW.md` lists every Italian string for a native check.

## Known limits

- Everything is a fixture. Replies are scripted, usage is made up, nothing runs and no Core, account or token is touched.
- Italian was written by the builders and is not native-checked (`IT-REVIEW.md`).
- The Light look is approved as is by the owner (2026-10-26); the contrast of every route is checked, but not on a real display.
- Checked in headless Chromium only: no real touch device, no screen reader, no Firefox or Safari, no real Windows High Contrast (forced colours were checked with Chromium's emulation), no 200 or 400 percent zoom.
- Map performance is measured in headless Chromium on a PC, not on a phone; above 60 nodes hulls are not separated.
- Not built: Ctrl+Enter, the Alt+1/2/3 and Ctrl+K shortcuts, view transitions, a duration-class table, round Tell, Places and Stop buttons on the phone, the font subset for production, the service worker.
- Pause all, Emergency stop and decisions act on the simulation only.
