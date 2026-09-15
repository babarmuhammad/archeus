# Track B — adopt zoetrope's session flow graph

Paste this whole file as the first message of a fresh session.

---

You are working in the archeus repo (D:\Claude) on branch `feat/session-flowgraph`, in a
dedicated git worktree. Three other agents are working the same repo in parallel on
`legal/site-compliance`, `chore/code-simplifier` and `feat/account-rotation`. Merge order is
A → D → B → C, so rebase onto main before you open a PR.

**A fifth agent — not one of the four — is already working directly on `main`,** in the primary
working tree (`D:\Claude`), with uncommitted changes and unpushed commits. This one affects you
directly:

- **Never touch the primary working tree.** No `git add`, commit, stash, checkout, reset, clean
  or branch switch in `D:\Claude`. Work only inside your own worktree.
- `git worktree add` branches from the last commit, so that agent's uncommitted edits are not in
  your tree. That is correct — do not try to pull them in.
- **`claude_sessions/gui_api.py` and `claude_sessions/web/app.js` are in flight on main right
  now** — the two files you append to. Expect a three-way conflict at merge. Resolve it by
  re-appending your entry at the end of the table as it stands after main's change, never by
  taking a whole-file side.
- **`harnesses.py`, `codex.py`, `pi.py`, `gui.py`, `main.py` and `web/index.html` are also in
  flight.** You read the first three to decide whether Codex and pi sessions can be supported —
  any version you read is provisional. Confirm the transcript shape against merged main before
  you commit support for those harnesses.
- `git fetch && git rebase origin/main` before opening a PR, then re-run the full gate list.

## Goal

Adopt the FUNCTION of https://github.com/furkankly/zoetrope — "watch a Claude Code or Codex
session as a live flow graph, in your terminal or your browser" — into archeus.

Zoetrope is Rust: a portable I/O-free core library, a native CLI frontend on ratatui, and a web
frontend on ratzilla compiled to WebAssembly. It treats a transcript as an append-only event
log and keeps **content time** (the session's own timestamps) separate from **presentation
time** (how long you spend watching). It offers: follow a live session, replay a finished one,
scrub, control playback speed, and inspect a node for its prompt, tool calls and timings.

Adopt the BEHAVIOUR, not the source. Read its LICENSE first. Do not copy Rust code, do not
vendor a crate, do not add a build step. If you take any wording, layout idea or data shape
from it, attribute that in the module docstring and in `docs/credits.md`. archeus is pure
stdlib Python plus vendored JavaScript served from loopback — keep it that way.

## Ownership fence

You may create or edit ONLY:

```
claude_sessions/flowgraph.py                        (new)
claude_sessions/web/flow.js, claude_sessions/web/flow.css   (new)
tests/test_flowgraph.py                             (new)
docs/sessions.md                                    (append one section)
notes/handoff-flowgraph.md                          (new)
claude_sessions/gui_api.py    APPEND ONE ENTRY at the end of GET_ROUTES (~line 4383). Nothing else in that file.
claude_sessions/web/app.js    at most 3 appended lines to open the view. Do not touch the NAV table at line 754.
```

You may NOT touch: `www/**`, `quota.py`, `accounts.py`, `usage.py`, `failover.py`, `app.css`,
`gui.py`, `CHANGELOG.md`, `docs/img/**`, `README.md`, `.github/FUNDING.yml`, `pyproject.toml`,
`packaging/**`, or any other test file.

Do NOT re-shoot screenshots — an integrator does one `tools/shot_gui.py --docs` run after all
four branches merge.

## Reuse before you build — the ladder stops early here

- `claude_sessions/transcripts.py` is THE ONE reader for `.jsonl` transcripts. Use `iter_json`
  with its `prefilter` / `limit` / `offset` / `max_bytes`. Never open a transcript yourself and
  never call `readlines()` — these files reach 100 MB and there is an AST gate enforcing the
  single reader.
- `claude_sessions/connections.py` already renders a self-contained interactive HTML graph with
  an embedded data blob and progressive disclosure. Read how it does the embedding, the caching
  and the palette (`TYPE_COLORS`) and follow that shape.
- `claude_sessions/render.py` for markup helpers, `store.py` for paths, `paths.py` for resolving
  a project's real cwd — never decode a project folder name.
- The `/graph` route is the model for serving an extra page: it is opened with `window.open()`
  and therefore CANNOT carry the `X-Claudectl` header, which is why it takes the per-run token
  in its query string (`?k=`). Your route does the same. Read `gui._guard` and the security
  bullets in CLAUDE.md before writing the handler — Host allowlist, `Sec-Fetch-Site` in
  (`same-origin`, `none`), and `hmac.compare_digest` fed BYTES.

## What to build

1. `flowgraph.py`: `build_events(transcript_path, limit=…)` returning typed events — user
   prompt, assistant turn, tool call with name and target and duration, result, error, subagent
   spawn, compaction — each carrying its own content timestamp, a parent link, and token/cost
   figures where the transcript has them. Streaming, bounded memory: assert with `tracemalloc`
   in the test that peak memory stays under a fraction of the file size. There is precedent for
   exactly this gate in the repo.
2. `render_flow_html(events, …)` producing one self-contained page: nodes laid out on the
   content-time axis, edges parent to child, colour by event type, a scrub bar, play/pause with
   a speed control, and a click-to-inspect side panel. Presentation time is independent of
   content time — a three-hour session must scrub in seconds.
3. **Live follow:** poll the transcript's tail from the existing offset and append new events.
   Reuse `iter_json`'s offset so a poll never re-parses the file. Poll no faster than 1s, and
   write DOM only when a value actually changed — this app has been bitten before by an
   unconditional `textContent=` inside a poll loop destroying and recreating nodes every tick.
4. Serve at `GET /flow?sid=…&k=<token>`, opened from the session row's action menu. Off-nav,
   like `/graph` — do NOT add a `NAV` entry, a `SECTIONS` id, or an `OFFNAV` row. That keeps
   your diff out of three tables other agents are also appending to.
5. **Codex and pi sessions:** archeus already reads those harnesses (`codex.py`, `pi.py`,
   `harnesses.py` — read only, do not edit). If their transcript shape maps cheaply, support
   them; if not, say so in the handoff and support Claude Code only. Do not half-support one.

## Constraints

- No new runtime dependency. Vendored JavaScript only; the GUI works offline.
- Animate `transform` and `opacity` ONLY. No `backdrop-filter`, no `filter: blur`, no
  `mix-blend-mode` — a test parses every `@keyframes` block and rejects any other property, and
  these are the exact causes of the Qt shell tearing.
- Anything that animates must stop on `document.hidden`, `!MO.vis`, `motion:off`, and
  `prefers-reduced-motion`.
- Reading a transcript must never fault on a malformed line — transcripts are user data, and
  `transcripts.py` already sets the `errors='replace'` policy.

## Verify

```
py -m pytest tests/test_flowgraph.py tests/test_endpoint_floor.py -q
py -m pytest -q
py tools/smoke_gui.py
py -m ruff check claude_sessions tools
```

The full suite must stay green. `tests/test_flowgraph.py` must cover: event extraction from a
fixture transcript, the memory ceiling, the route's guard rejecting a missing or wrong token,
and a malformed line not raising.

## Handoff

`notes/handoff-flowgraph.md` — what landed, what you dropped from zoetrope's feature set and
why, the CHANGELOG lines for the integrator, and an explicit note that screenshots need
re-shooting after merge.

Do not edit `CHANGELOG.md`. End every commit message with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
