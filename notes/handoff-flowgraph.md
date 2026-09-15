# Handoff — Track B, session flow graph (`feat/session-flowgraph`)

Adopts the FUNCTION of [zoetrope](https://github.com/furkankly/zoetrope) (MIT, © 2026 Furkan
Kalaycioglu): watch a coding-agent session as a live flow graph, replay a finished one, scrub
it, inspect a node. No Rust was copied, no crate is vendored, no build step was added.
Attribution is in `flowgraph.py`'s module docstring and in `docs/credits.md`.

## What landed

| File | |
|---|---|
| `claude_sessions/flowgraph.py` | new — streaming event extraction for all three harnesses + the page renderer |
| `claude_sessions/web/flow.js` / `flow.css` | new — canvas graph, controls, inspector, follow poll |
| `claude_sessions/gui.py` | `GET /flow` branch beside `/graph`, and `_serve_flow` |
| `claude_sessions/web/app.js` | one **Flow** button in the session detail pane + `flowS(i)` (3 lines) |
| `tests/test_flowgraph.py` | new — 23 tests |
| `docs/sessions.md` | one appended section; `docs/credits.md` one appended bullet |

`build_events(path, harness=…, limit=…, offset=…)` is a **generator** over
`transcripts.iter_json` — the one reader — yielding
`{o, t, type, lane, name, target, dur, ref, tok_in, tok_out, text}`. Text is truncated at
`TEXT_CAP` where it is read, so the payload cannot grow with the file.
`tail_events(path, offset)` is the follow poll; `render_flow_html(events, meta)` is the page,
built the way `connections.render_html` is (one template, `_script_json` for every blob,
`html.escape` for the one value that reaches markup).

## Decisions worth knowing at merge

- **`/flow` is a real page, not a `GET_ROUTES` entry.** The user chose this over the
  fence-safe JSON variant. It is opened with `window.open()`, which cannot attach the
  `X-Archeus` header, so the token rides the query string and `_token_ok` runs in `do_GET` —
  exactly the position `/graph` occupies. That means **`gui.py` is touched**, and `gui.py` was
  in flight on `main`. Re-apply the branch after whatever main did; never take a whole-file
  side.
- **One route, two answers.** `?since=<offset>` returns the new events as JSON instead of the
  page. A second endpoint would be a second guard to keep in step, and the page already holds
  the only credential either would need.
- **No `NAV` / `SECTIONS` / `OFFNAV` entry**, deliberately: it is a separate window like
  `/graph`, so none of the page gates apply and the diff stays out of three tables the other
  tracks are also appending to.
- **A `ref` is counted BACKWARDS in events, never an absolute index.** A follow poll parses
  its own batch and cannot know how many events the page already holds.
- **Per-harness parsing lives in `flowgraph.py`**, dispatched on `harnesses.of_path()['id']`,
  rather than as a new `'flow'` key in the `harnesses.py` descriptor table — that file is one
  of the ones this track is fenced out of, and `store.transcript_path` already places a file
  the same way. If the fence goes away, moving it into the descriptor is a clean follow-up.

## What the transcripts actually carry (checked against real files here)

- **No harness records a tool's duration.** It is derived: the gap between the call and the
  result that closed it, paired by `tool_use.id` ↔ `tool_result.tool_use_id`. So the **result**
  carries `dur` and points back at the call — a generator cannot patch what it already yielded,
  and it will not buffer a transcript in order to.
- **A Codex rollout records every turn twice** (the `event_msg` the UI showed and the
  `response_item` the model was sent, plus a developer preamble and `<environment_context>`
  wearing the same shape). Taking both drew every prompt twice.
- **Codex `token_count` is cumulative** — reported as a delta, as `codex.fold` already does.
- **No compaction marker and no `isSidechain: true` exists in this machine's corpus.** Both are
  matched defensively; nothing depends on seeing one, and `SUPPORTS` says per harness what its
  file actually carries rather than what it could in principle record.
- **Codex tool calls are unverified**: `response_item` `function_call` / `function_call_output`
  is implemented and tested against a fixture, but no rollout on this machine has run a tool.
  Same for pi's tool blocks, where both spellings (`toolUse`/`tool_use`, `toolResult`/
  `tool_result`) are accepted because guessing one would silently draw nothing.
- **An assistant line that is only a `tool_use` is not a turn** and is not drawn — it put a
  blank node in front of every tool call.
- **A prompt is judged per BLOCK.** `transcript._message` joins the blocks and then tests the
  result, so a turn whose first block is a `<system-reminder>` loses the real prompt with it.
  That bug is still live in the transcript drawer — **not fixed here**, it is another track's
  file.

## Dropped from zoetrope's feature set, and why

- **Minimap** — the scrub bar plus a full-height rule at every prompt covers "where am I", and
  a second canvas is a second thing to keep in step with the first.
- **Gap compression as a TOGGLE** — the clamped axis is always on (8 s is the longest idle it
  pays pixels for). Two axes means two answers to "where is this event", and the real
  timestamps are in the clock and the inspector.
- **`[` / `]` era navigation** — the prompt rules make eras visible; keyboard era-hopping can
  follow if anyone asks for it.
- **Terminal frontend** — zoetrope has one. This is the GUI only; the TUI surface would be a
  separate piece of work with its own parity gates.

## For the integrator

- **Screenshots need re-shooting after merge** — `py tools/shot_gui.py --docs`, then
  `py tools/shot_tui.py`, then `py tools/optimize_images.py`. Nothing here re-shot them, per
  the parallel-track rules. The session detail pane has a new button, so the sessions capture
  is stale.
- `CHANGELOG.md` was not edited. Suggested entries:

```
### Added
- **Session flow graph** — open any session as a live flow graph (**Flow**, beside *Transcript*
  in the session detail pane): prompts, model turns, tool calls, results, errors and subagent
  lanes on the session's own clock, with play/pause, speed, scrub, wheel-zoom and a
  click-to-inspect panel. Idle gaps are clamped, so a twelve-hour session replays in seconds,
  and **Follow** appends a session that is still running. Claude Code, Codex and pi.
  Behaviour adopted from [zoetrope](https://github.com/furkankly/zoetrope) (MIT).
```

- Gates run on this branch: full suite **2356 passed, 1 skipped**; `tools/smoke_gui.py`
  **FAILURES: none**; `ruff check claude_sessions tools` clean. Verified by hand against a
  real 1,800-event session in Chromium: no console errors, the inspector reports a tool's
  duration, playback and scrub both move the playhead.
- Not covered by `smoke_gui.py`: it walks `NAV`, and this window is off-nav — the same blind
  spot `/graph` has. `tests/test_flowgraph.py` drives the route over real HTTP instead.
