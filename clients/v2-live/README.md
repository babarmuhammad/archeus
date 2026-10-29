# V2 Live

A prototype of the Archeus V2 app that runs entirely on a fixture simulation: no Core, no network, no build step. Every screen says SIMULATED. Audience: internal review. It is the reference for look, layout, behaviour and wording when the real V2 UI is built (`SPEC.md` is the acceptance checklist).

## Run it

- Windows: double-click `start.cmd` (serves this folder on `http://127.0.0.1:8000` with `py -m http.server` or `python -m http.server`, then opens the browser). Close the server window to stop.
- Any OS: `python -m http.server 8000 --bind 127.0.0.1` in this folder, open `http://127.0.0.1:8000/`.
- It must be served over http, not opened as a file (ES modules).

## Open it on your phone

The prototype is fixture data only, so it is safe to show on a phone on your own network. Binding the network is on demand and the firewall stays your decision.

1. Double-click `start-lan.cmd` (or run `start-lan.cmd 8895` for another port). It finds the PC's private Wi-Fi or Ethernet IPv4 address, refuses 0.0.0.0 and any VPN or virtual adapter, prints `http://<that address>:<port>/` and a warning that anyone on the network can open the prototype, then serves in that window. Close the window to stop. It never opens the firewall and never opens a browser.
2. Windows blocks other devices by default. Once, in an administrator PowerShell, allow that port from the local subnet only:
   `New-NetFirewallRule -DisplayName "Archeus proto" -Direction Inbound -Protocol TCP -LocalPort <port> -RemoteAddress LocalSubnet -Profile Public -Action Allow`
   Remove it when you are done: `Remove-NetFirewallRule -DisplayName "Archeus proto"`. (`-Profile Public` is what a Wi-Fi network marked Public needs; use `Private` if the network is Private.)
3. On the phone, on the same Wi-Fi, open the printed address. `?story=huge&device=auto` shows 100 projects at the phone's own size; `device=auto` makes the app fill the screen.
4. Add to Home Screen gives an icon and a full-screen launch. Over plain http a phone does not treat the page as installable (no service worker, no install prompt, nothing offline), so Add to Home Screen is all there is. The 180 px `apple-touch-icon.png` was made from `icon-512.png` (a resize, no new art); the star fills 62 % of the icon, inside the 80 % maskable safe zone, so one picture serves the `any` and `maskable` manifest entries.

## URL options

Options go in the query string, for example `index.html?theme=light&lang=it&sim=paused#/now`. The URL wins over what the app stored and is not stored itself.

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
| `story` | `calm` | finished-work fixture with Tell, Today and known projects |
| `projects` | `10` to `100`, `local` | that many simulated projects; `local` builds this machine's own from `local/projects.local.json` (gitignored; written by `py tools/v2_live_local_projects.py`, names and counts only), and the Tools menu lists it only when the file exists |
| `look` | `app`, `ansi`, `hc`, `mono` | terminal colours |
| `ascii` | `1`, `0` | terminal ASCII glyphs on or off |
| `sr` | `1`, `0` | terminal linear Read mode on or off |

## Routes

`#/now`, `#/work` (the graph and the list of what is happening and what needs you; `#/attention` and `#/attention/<id>` redirect to `#/work` and `#/work/<id>`), `#/replay/<mission>`, `#/chat`, `#/security`, `#/health`, `#/usage`, `#/accounts`, `#/extensions`, `#/settings`, `#/terminal`. `#/more` and `#/map` redirect to `#/now`; on a phone the Places sheet replaces the old More page. A thing opens in a details sheet at `#/<route>/<id>`: missions `m-`, tasks `t-`, executions `x-`, plans `p-`, approvals `a-`, verifications `v-`, ideas `i-`, knowledge `k-`, projects `prj-`, accounts `acc-`, hooks `h-`, MCP servers `mcp-`, agents `ag-`. Examples: `#/work/m-date`, `#/attention/a-1`, `#/replay/m-date`.

## Devices

The toolbar's Device button picks Auto (fills the window), Phone 390, Tablet 820, Desktop 1440, Terminal (a text-mode view of the same state), or All devices: four live panes side by side, each laid out at its own real width, all driven by one simulation (act in one pane and the others change). Wide frames are scaled down to fit the window, which the note under the toolbar says. On phones a five slot bottom bar gives Overview, Work (with the count of what needs you), Tell (the filled middle button), Places and Stop (Re-arm when stopped). Places opens a full height sheet with search, the destinations as tiles and the top five projects. Stop asks twice in a sheet, with the confirm on the side away from the thumb. The top bar carries the star (Overview), the page title, the SIMULATED tag, the status word (safety sheet) and search; when the window itself is the phone the toolbar row folds into the SIMULATED tag, which opens a Prototype tools sheet. A phone frame on a desktop window keeps the toolbar. No scrollbars are drawn on a phone.

## Simulation controls

Toolbar, Sim button (and Settings, Simulation): Play or Pause, speed x0.5 to x8, Trigger an approval, Inject a failure, Break the harness (trips the spawn breaker), Go offline or Reconnect, Reset. One real second is ten simulated seconds at x1. Pause all, Resume all and Emergency stop are in the top-bar safety dialog and Settings; the emergency stop asks first, blocks new dispatch until re-armed (also possible while nothing runs) and Re-arm asks again.

## Keyboard

`?` lists the keys. `j` and `k` move through list rows and cards, Enter acts on the focused row or card, Space opens a row, Esc closes the help, a menu, an ask-first question or the details sheet. Focus order: toolbar, navigation, page, chat bar, bottom bar, then the details sheet (it takes focus when it opens and gives it back). The terminal view has its own keys (`?` there). The chat bar takes `/` for the 34 slash commands (English names, Italian aliases).

## Tests and probes

Run from the repository root; the repo's shared lock keeps heavy runs from overlapping.

| What | Command |
|---|---|
| unit tests (sim, spine, terminal, chat, replay, map) | `node --test clients/v2-live/test/*.test.mjs clients/v2-live/js/constellation/*.test.mjs` |
| layout probe: every route and overlay, 14 viewports, dark and light, overlap, clipping, targets, contrast, console errors, the motion invariant (only the allowed loops) | `py tools\v2_live_layout_probe.py` (`--lang it`, `--routes now,now~details`, `--viewports 390x844`) |
| map probe | `py tools\v2_livemap_probe.py` |
| design kit probe | `py tools\v2_live_design_probe.py` |
| All devices hit-test | `py tools\v2_live_alldevices_probe.py` |
| phone foundation: one threshold, PWA bits, safe areas, 44 px targets, no sideways scroll at 320 to 430 and 200 %, landscape flips to the phone shell; the bar, top bar, sheets and toasts under a faked keyboard and injected insets; one vertical scroll surface per route (known nested scrollers are listed as expected failures with their owner) | `py -I tools2_live_phone_probe.py` |
| phone shell in a real browser: bar slots, Places, palette, Stop two step, safety and tools sheets, language, phone frame on desktop | `py -I tools2_live_phone_functional.py` |
| functional runs | `py tools\v2_live_s3_functional.py`, `v2_live_s4_functional.py`, `v2_live_tui_check.py`, `v2_live_s6_functional.py` |
| package | `py tools\v2_live_package.py` writes `Archeus-V2-Live.zip` (this folder without tests, `start.cmd`, `README-FIRST.txt`) |

## Files

`index.html`, `css/` (tokens, app, areas, chat, tui), `js/` (shell `app.js`, views, inspectors, areas, chat, Replay, keyboard, terminal view in `js/tui/`, map in `js/constellation/`), `sim.js` (the simulation, no DOM), `chat-engine.js` and `slash.js` (the one chat and command brain), `spine-model.js`, `core-words.js`, `replay-model.js`, `term.js`. `SPEC.md` is the feature inventory with status words BUILT, DESIGNED, PROTOTYPED and SIMULATED. `IT-REVIEW.md` lists every Italian string for a native check.

## Known limits

- The phone shell flips for a phone held sideways through CSS container style queries (`style(--phone: 1)` beside the width test). That needs Chrome or Edge 111, Safari 18 or a recent Firefox; in an older browser the desktop layout rules are dropped.
- Everything is a fixture. Replies are scripted, usage is made up, nothing runs and no Core, account or token is touched.
- Italian was written by the builders and is not native-checked (`IT-REVIEW.md`).
- The Light look is approved as is by the owner (2026-10-26); the contrast of every route is checked, but not on a real display.
- Checked in headless Chromium only: no real touch device, no screen reader, no Firefox or Safari, no real Windows High Contrast (forced colours were checked with Chromium's emulation), no 200 or 400 percent zoom.
- The Overview rings and the core (branch v2/live-net) are not drawn under 600 px: the phone keeps its own scene. Rings carry colour only; project names are drawn for a bounded set (SPEC RG05), the rest are reachable by Tab and in the node table.
- Map performance (the Overview map) is measured in headless Chromium on a PC, not on a phone; above 60 nodes hulls are not separated.
- Not built: Ctrl+Enter, the Alt+1/2/3 and Ctrl+K shortcuts, view transitions, a duration-class table, the font subset for production, the service worker.
- Pause all, Emergency stop and decisions act on the simulation only.
