# Local Archeus Environment (V1) — developer runbook

**Developer/test tooling, not part of Archeus.** `tools/v1_env.py` (and its double-click wrapper
`tools/archeus-v1.bat`) starts the V1 system you already have, waits until it is really healthy,
opens its app, and stops it cleanly. It is not in the wheel, it is not a CLI verb, it adds no
route, no flag and no security exception to Core, and it changes nothing P9–P18 do. It exists so
manual testing of this phase and the next ones is one double-click instead of a list of commands.
It never records test results: every manual check below is yours to perform and to record.

## What actually runs

One process: **Core** — `archeus core`, run through the console script's own entry
(`claude_sessions.cli:run`) from this checkout. It holds the engine and every worker thread, the
HTTP API and SSE streams on `127.0.0.1:7337` (a fixed port, loopback only), and it serves the
built SPA from `archeus/api/static/`. Everything else is a client of it over HTTP: the browser,
`archeus tui`, and every other `archeus` verb. There is no separate API server and no Vite dev
server; the SPA is a build.

The launcher adds nothing to Core:

| | what it uses |
|---|---|
| start | the real `archeus core` (with your `--remote-host`, if any), output captured to a file |
| ready | discovery reports `running` for the pid it started, **and** `/v1/health` answers with every component `running` or `idle` (so not while the engine is still reconciling, and never with a component `failed`) |
| app URL | the one `archeus core --open` opens: `http://127.0.0.1:7337/#launch=<code>`, a one-time code from `/v1/devices/launch/code` with the local user's full grant |
| watch | `/v1/health` every 2 s; the child's exit |
| stop | the signal `archeus core` already handles (Ctrl+Break on Windows, SIGTERM elsewhere); after 30 s, a kill of Core's own process. **Never a process-tree kill**: executions are detached by design and the next Core adopts or reconciles them (P11). To stop executions use `archeus estop`. |
| a Core already running | it opens that Core's app and leaves it running; it never stops a Core it did not start |

Lifecycle, as printed in the window: `STARTING → HEALTHY → RUNNING → STOPPING → STOPPED`, or
`FAILED` with the exit code, what it means, and the two log paths. After `HEALTHY` it also prints
`UNHEALTHY: …` if `/v1/health` stops answering or a component fails, and `HEALTHY: again` if it
recovers.

## Prerequisites

- Python 3.10+ (the `py` launcher, or `python` on PATH). Archeus has no runtime dependencies.
- Node, **only to build the app**, once and again whenever `clients/app` changes:

  ```powershell
  cd clients\app; npm ci; npm run build
  ```

  The launcher refuses to start without a build, and warns when the build is older than
  `clients/app/src` (you would be testing yesterday's UI).
- Optional, recommended: `py -m pip install -e .` in the checkout, so `archeus` on your PATH is
  this checkout. Without it, spell a verb as
  `py -c "from claude_sessions.cli import run; run()" status`. (`py -m claude_sessions` does
  **not** route the V1 verbs; the console-script entry does.)

## First-time setup: the desktop shortcut (Windows)

```powershell
py tools\v1_env.py --install-shortcut      # makes "Archeus V1" on your desktop
py tools\v1_env.py --remove-shortcut       # removes it
```

The shortcut points at `tools\archeus-v1.bat` in **this** checkout; the desktop folder is asked
of Windows (it follows OneDrive redirection). Nothing about your machine is written into the
repository. If you move or re-clone the checkout, run `--install-shortcut` again from the new one.

## Start, stop, restart

- **Start**: double-click **Archeus V1**. Or `tools\archeus-v1.bat`, or `py tools\v1_env.py`
  (macOS/Linux: `python3 tools/v1_env.py`; the shortcut is Windows-only, the launcher is not).
  Flags: `--no-browser`, `--remote-host H` (repeatable, passed to `archeus core`),
  `--timeout S` (default 60).
- **The app** opens in your default browser once Core is healthy. To open it again later: run the
  launcher again (it finds the running Core and opens a fresh link), or `archeus core --open`.
  Reloading a tab keeps working; a link's code works once.
- **Stop**: **Ctrl+C in the launcher window.** You see `STOPPING`, then
  `STOPPED: Core exited 0 (stopped cleanly)`. cmd then asks `Terminate batch job (Y/N)?`:
  either answer is fine. **Closing the window with its X kills Core** instead of stopping it —
  Windows gives a console process no time to finish. Core recovers from that on its next start
  (it is the crash path), but use Ctrl+C when you want a clean stop.
- **Restart Core**: Ctrl+C, then double-click again. An open app tab reconnects by itself, which
  is also the manual reconnect test.

## Logs

The home is `%LOCALAPPDATA%\Archeus` (or `ARCHEUS_HOME`), shown on the launcher's first line.

| file | what |
|---|---|
| `<home>\logs\core.log` | Core's own log: every request, every worker event (kept across runs) |
| `<home>\logs\dev-core-output.log` | Core's console output for this launch (overwritten each launch; echoed in the window as `core \| …`) |

`Get-Content "$env:LOCALAPPDATA\Archeus\logs\core.log" -Wait -Tail 20` follows it live.

## Using the CLI and the TUI alongside

With the environment running, from any terminal (same `ARCHEUS_HOME`, if you set one):
`archeus status`, `archeus devices`, `archeus sessions`, `archeus terms`, `archeus route why <id>`,
`archeus verify <mission>`, `archeus estop`, `archeus automation list`, `archeus tui`. They find
Core through discovery; none of them starts one.

**This is a real Core.** It runs the real Claude Code adapter, gated by the provider-terms
answers: `archeus terms` shows them, `unknown` blocks every real call, and
`archeus terms claude_code permit` allows them — after which missions do real work and spend
your quota.

## A separate home, and resetting the database

To test on a throwaway home, set `ARCHEUS_HOME` in the terminal you start from, and in every
terminal you use the CLI from:

```powershell
$env:ARCHEUS_HOME = "$env:TEMP\archeus-scratch"; tools\archeus-v1.bat
```

Only one Core can run at a time on this machine (the port is fixed), whatever the home.

**Reset** = stop Core, then move the home aside (never while Core runs):

```powershell
Rename-Item "$env:LOCALAPPDATA\Archeus" ("Archeus.bak-" + (Get-Date -Format yyyyMMdd-HHmm))
```

The next start creates a fresh database, a fresh local token and no paired devices, projects or
provider-terms answers. Your legacy data (`~/.claude`, `<project>/.archeus`) is not in the home
and is not touched. Put the backup back by renaming it again (with Core stopped).

## Tests and judges

The suites never attach to a running Core: each test starts its own Core on a temporary home and a
free port, with the fake harness, so they can run while the environment is up and never touch its
home. Run them from the checkout:

```powershell
py -m pytest tests\v1 -q                                  # all V1 tests (judges included)
py -m pytest tests\v1\judge -q                            # the judge suites only
$env:ARCHEUS_E2E = '1'; py -m pytest tests\v1\e2e -q      # browser/G3 (Playwright + Chromium)
cd clients\app; npm test                                  # the SPA's own tests
py tools\mutate_p18.py                                    # a phase's mutation suite
```

A mutation suite **edits source files while it runs**: do not edit, and do not restart the
environment, until it has finished — a Core started mid-run would load a mutant.

## Failure and recovery, safely

| scenario | how | what you should see |
|---|---|---|
| Core dies | `archeus status` for the pid, then `taskkill /F /PID <that pid>` (that pid only, never `/T`) | launcher: `FAILED: Core exited 1 (killed or crashed)` and the log paths; the app shows it is disconnected. Relaunch: the tab reconnects |
| port taken | another program on 7337 | `FAILED: Core exited 2 (its port is in use by another program)` and Core's own message |
| started twice | double-click again while running | `ALREADY RUNNING …`; the app opens; nothing new starts, nothing is stopped |
| e-stop | `archeus estop` | executions stop; Core stays disarmed (the next start says `DISARMED`) until a device re-arms it in the app |
| app not built / stale | skip `npm run build` | not started (no build), or a warning (stale) |

## P18 manual acceptance (yours to perform and record)

The three items owed by P18 (p18-design-gate §22.2.1, "Manual evidence still owed"). The
launcher measures nothing and records nothing; automated touch emulation in the browser tests is
**not** a substitute for item C.

**A. 60 fps on integrated graphics.** On a machine with integrated graphics (Intel UHD class),
Edge or Chrome:

1. Start the environment on the home that holds your real projects (the default home), so the
   graph is large: open **World**, a project, and its graph view, or
   `#/world/graph/project/<id>` for the largest project.
2. In DevTools → Console, the node count: `document.querySelector('[data-graph-nodes]').dataset.graphNodes`,
   and the loop state: `data-graph-loop` (`running` / `parked`) on the same element.
3. DevTools → Performance: record while pressing `+`, `-` and `0` a few times, and while a
   running execution pulses (start a mission that executes). Frames must stay ≤ 16.7 ms during
   camera moves and pulses, and there must be no frames at all while idle (the loop parks).
4. Record: machine, GPU, browser and version, `data-graph-nodes`, the worst frame time, and the
   idle behaviour, in the gate's §22.

**B. Windows Terminal and conhost (P17 carry-over).** With the environment running:

1. Windows Terminal: `archeus tui`. Classic console: run `conhost.exe powershell`, then
   `archeus tui` in that window.
2. In each: the state glyphs render (or, with `$env:ARCHEUS_TUI_ASCII = '1'`, the ASCII set);
   colours follow the dark default and `archeus tui --light`; a resize redraws with no stray
   lines; `1`–`4` and `a` switch destinations; Enter opens an inspector; `q` quits and leaves the
   prompt usable. (`archeus tui --once` prints one frame, for a quick look.)
3. Record any difference between the two consoles.

**C. A physical touch device.**

- *A touch screen on this machine* (a touch laptop, ≥ 600 px wide): nothing extra — the app is
  already on `127.0.0.1`.
- *A tablet or phone*: Core binds loopback only and there is no LAN mode; the one supported way in
  is an authenticated tunnel **you** set up (p15-design-gate §8; Tailscale Serve recommended),
  deliberately and for the test only:
  1. expose `127.0.0.1:7337` through the tunnel (Tailscale: `tailscale serve --bg 7337`; check
     the command against your Tailscale version, and that the tunnel passes the original `Host`
     header through, which P15 requires);
  2. start with the tunnel's name: `py tools\v1_env.py --remote-host <machine>.<tailnet>.ts.net`;
  3. `archeus pair --name tablet` and open the printed link on the device (the code works once,
     for 120 s); every request is still authenticated;
  4. afterwards: `archeus devices revoke <id>`, stop the tunnel, restart without `--remote-host`.
- Check, at ≥ 600 px: a two-finger pinch zooms around the fingers; one tap selects a node and a
  double-tap opens its inspector; the graph toolbar's controls are comfortable to tap (44 px).
  Then on a phone (< 600 px): no canvas is drawn, and the Relations list (or the note and link)
  is shown instead.
- Record the device and the browser.

## Troubleshooting

| symptom | cause / fix |
|---|---|
| `not started: the app is not built` | `cd clients\app; npm ci; npm run build` |
| `FAILED: … its port is in use` | something else listens on 7337 (another Archeus home's Core, or another program): stop it |
| `FAILED: … another Core holds this home` | a Core for this home is starting or running elsewhere; `archeus status` |
| `a Core holds this home but its discovery file is unreadable` | a Core is starting or dying; wait a moment and retry |
| `not healthy after 60s (still: engine reconciling)` | the boot sweep is slow (many executions to reconcile); retry with `--timeout 180` and read `core.log` |
| `DISARMED` at start | an e-stop is in force; re-arm from a device in the app |
| the window closed at once | start `tools\archeus-v1.bat` from a terminal to see why, or read `dev-core-output.log` |
| `archeus` is not recognised | `py -m pip install -e .`, or the `py -c "from claude_sessions.cli import run; run()" <verb>` form |

## Removing it

`py tools\v1_env.py --remove-shortcut`. The launcher is two files in `tools/` with no state of
its own besides `<home>\logs\dev-core-output.log`; nothing else depends on them.
