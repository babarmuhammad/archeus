# Track D — automatic account rotation on quota exhaustion

Paste this whole file as the first message of a fresh session.

---

You are working in the archeus repo (D:\Claude) on branch `feat/account-rotation`, in a
dedicated git worktree. Three other agents are working the same repo in parallel on
`legal/site-compliance`, `feat/session-flowgraph` and `chore/code-simplifier`. Merge order is
A → D → B → C, so you go in second: rebase onto main once A lands.

**A fifth agent — not one of the four — is already working directly on `main`,** in the primary
working tree (`D:\Claude`), with uncommitted changes and unpushed commits. This one affects you
directly:

- **Never touch the primary working tree.** No `git add`, commit, stash, checkout, reset, clean
  or branch switch in `D:\Claude`. Work only inside your own worktree.
- `git worktree add` branches from the last commit, so that agent's uncommitted edits are not in
  your tree. That is correct — do not try to pull them in.
- **`claude_sessions/gui_api.py` and `claude_sessions/web/app.js` are in flight on main right
  now** — the two files you append to. Expect a three-way conflict at merge. Resolve it by
  re-appending your entries at the end of `GET_ROUTES`, `POST_ROUTES` and `PARAM_CHECKS` as they
  stand after main's change, never by taking a whole-file side.
- `harnesses.py`, `codex.py`, `pi.py`, `gui.py`, `main.py` and `web/index.html` are also in
  flight. You do not own them; do not edit them, and treat anything you read there as
  provisional. If your quota or usage work needs a change in one of those, raise it in the
  handoff instead of making it.
- `git fetch && git rebase origin/main` before opening a PR, then re-run the full gate list.

## Goal

Adopt the function of https://github.com/DevDock-AI/claude-unlimited: when one account runs out,
work continues on the next one automatically, without interrupting the session.

That project is a local Python daemon on `127.0.0.1:4317` that pools Claude Pro/Max, Codex and
API-key credentials. It keeps clients on one account — **sticky** — until it crosses a usage
threshold (default 98%) or hits a real quota limit, then routes the next request to the next
enabled account. The real credential is substituted server-side only and never returned to the
client. Credentials sit in OS keystores, config in `~/.claude-unlimited/config.json`, usage
history as JSONL, with a local dashboard.

Adopt the BEHAVIOUR. Check its LICENSE before reusing any code; prefer reimplementing on
archeus's own machinery, which already has most of it.

## Ownership fence

You may create or edit ONLY:

```
claude_sessions/rotate.py                           (new)
claude_sessions/quota.py, usage.py, accounts.py, failover.py
tests/test_rotate.py                                (new)
docs/accounts.md, docs/providers.md                 (append sections)
notes/handoff-rotation.md                           (new)
claude_sessions/gui_api.py   APPEND at the end of GET_ROUTES (~4383) and POST_ROUTES (~4459),
                             plus a PARAM_CHECKS entry if you add a new parameter name.
                             Change nothing else in that file.
claude_sessions/web/app.js   append only; do not touch the NAV table at line 754.
```

You may NOT touch: `www/**`, `connections.py`, `flowgraph.py`, `app.css`, `gui.py`,
`CHANGELOG.md`, `docs/img/**`, `README.md`, `.github/FUNDING.yml`, `pyproject.toml`,
`packaging/**`, or any other test file. Do NOT re-shoot screenshots.

The reference repo carries a Ko-fi badge and a donation line in its README. That is NOT part of
this task — another branch owns the project's funding links. Adopt the rotation daemon's
behaviour only; add no badge, no donation copy, and no funding metadata anywhere.

## Reuse before you build — every piece of this already half-exists here

- `proxy_base.py`: detached child process, lock file, readiness handshake, request guard. Both
  existing daemons are built on it and yours must be too.
- `failover.py`: already sits between `claude.exe` and upstream and rewrites a request's `model`
  when a turn errors before any response byte has reached the client. Request-level retry IS
  per-turn failover, because every Claude Code turn is its own POST. Decide and justify: extend
  `failover.py` with account rotation, or write a sibling module. Its contract is that it never
  re-serialises a response body — there is a test enforcing that, and rotation must not break it.
- `quota.py`: already reads `usage.py`'s cached poll (never the network), fails open, gates only
  `claude … -p`, and has `note_failure()` to latch an account after a real refusal. Your
  threshold and switch decision belongs HERE, not in a new parallel copy.
- `usage.py`: the 300s background OAuth poll and its cache. Also check whether Claude Code's
  statusline payload — which already carries `rate_limits.five_hour` and `seven_day` — is a
  cheaper signal than the poll.
- `accounts.py` plus `config.all_config_dirs()`: the account roster. Do not invent a second one.

## Hard constraints — read twice, two of them are the whole design

1. **archeus NEVER writes `.credentials.json`.** Standing policy: refreshing a token can
   invalidate the refresh token and lock an account out of Claude Code entirely. claude-unlimited
   substitutes credentials server-side. Before you implement anything that READS another
   account's OAuth token and injects it into a request, **STOP and put the question to the user
   with the trade-offs.** The safe design that needs no credential handling at all is switching
   `CLAUDE_CONFIG_DIR` at spawn time and rotating which account new work starts on — start there,
   and state plainly what it cannot do (it cannot rotate mid-session without a restart).
2. **`quota.is_limit_error` must match what Claude Code actually says**, not what the markers
   assume. The real refusal is
   ```
   You've hit your session limit · resets 2:30am (Europe/Rome)
   ```
   with `"error":"rate_limit"` and `"apiErrorStatus":429` in the transcript, and it matched NONE
   of the old markers — so the latch had never once fired for the commonest rejection. With
   `--output-format json` that sentence lands in `result` behind ~200 characters of metadata and
   every reporter truncates it; `gui_api._claude_failure_reason` unwraps it. Verify against real
   strings, add the ones that are missing, and test with the literal text above.
3. **The daemon's guard is not optional.** It forwards the user's upstream credential on a fixed,
   source-published port, so an unauthenticated request spends their quota — a CORS-simple
   `fetch()` from any open tab is enough, no DNS rebinding required. Three layers, cheapest
   first: Host allowlist; reject browser fetch metadata (`Origin`, `Referer`, `Sec-Fetch-*` —
   Claude Code's HTTP client sends none of them); per-run secret compared with
   `hmac.compare_digest` fed BYTES (headers decode as latin-1, and a non-ASCII one raises
   `TypeError` straight into `socketserver.handle_error`).
4. **Fail open.** An account with no poll data, a stale cache, or a cold start must pass through.
   A rotation layer that blocks work because a background thread has not run yet is worse than
   the bug it fixes.
5. **Sticky.** Do not round-robin per request. Stay on one account until it crosses the threshold
   or hits a real limit — switching per request fragments prompt caching and multiplies cost.
6. Detached child process with `CREATE_NEW_CONSOLE` (per `failover.py`'s reasoning: the user can
   close archeus and live sessions must survive), lock file, readiness handshake — all from
   `proxy_base`.
7. Nothing in tests may spawn a real `claude` process. `conftest` guards `Popen` by inspecting
   argv; respect it.

## Deliver

- A rotation policy with a configurable threshold (default 98%, matching the reference) and an
  explicit per-account enable flag, stored through the existing settings reader and writer.
  `load_settings` must carry keys it does not recognise — an older build must not erase a newer
  one's settings.
- A rotation event log through `events.record()`. Its dedupe key must not contain a measurement:
  a key with a decimal in it never dedupes, and that once filled 609 of 674 log slots and evicted
  every real failure. Digits that are identity stay; decimals collapse.
- A GUI surface: which account is live, each account's headroom, the last N rotation events, and
  a manual "switch now". Feed gauges through `INST.set()` from the renderer that already fetched
  the numbers — an instrument never makes its own request, and its liveness must come from a live
  thing (running jobs), never from throughput, or it animates forever after one token is spent.
  Extend the existing ring with segments rather than adding a new gauge type.
- Any interactive TUI primitive reached from a GUI job thread HANGS rather than erroring. Only
  five are bridged: `ui.flash`, `ui.text_input`, `ui.confirm`, `diffview.confirm`,
  `claude_md._pager_confirm`. Keep the non-interactive core and the TUI wrapper split, the way
  `skills.py` does it.

## Verify

```
py -m pytest tests/test_rotate.py tests/test_quota.py tests/test_endpoint_floor.py -q
py -m pytest -q
py tools/smoke_gui.py
py -m ruff check claude_sessions tools
```

`tests/test_rotate.py` must cover: the real limit sentence above latching the account; threshold
crossing selecting the next enabled account; stickiness (no switch below threshold); fail-open on
an empty cache; and the guard rejecting both an unauthenticated request and a browser-shaped one.

## Handoff

`notes/handoff-rotation.md` — the design you chose, the credential question and the user's
answer, what does NOT work (mid-session rotation without a restart, if that is where you landed),
and the CHANGELOG lines for the integrator.

Do not edit `CHANGELOG.md`. End every commit message with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
