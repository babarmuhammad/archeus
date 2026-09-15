# Track D — automatic account rotation (branch `feat/account-rotation`)

Adopts the *function* of [DevDock-AI/claude-unlimited](https://github.com/DevDock-AI/claude-unlimited):
when one Claude account runs out, work continues on the next one. It does **not** adopt its
mechanism, and the reason is the bulk of this note.

---

## The credential question, and the answer

The track prompt required this to stop and ask before anything read another account's OAuth
token. It was put to the user with the trade-offs, and the answer was to research it properly
first. What that turned up decided the design three times over.

**1. Anthropic's own documentation draws the line exactly between the two candidate designs.**
`docs.claude.com/en/docs/claude-code/legal-and-compliance` (this section reported effective
20 Feb 2026) permits:

> …an end user from signing in to the unmodified Claude Code binary with their own Claude
> subscription…

which is precisely what one `CLAUDE_CONFIG_DIR` per account, launching the real binary, is.
The same paragraph says:

> …developers may not collect, store, or intermediate Claude.ai credentials or session tokens…

A local proxy that swaps a bearer token, and a tool that copies `.credentials.json` blobs
between accounts, are both that verb. The Consumer Terms add "bypassing any of our systems or
protective measures", and a rate limit is a protective measure. Reporting the wording, not
giving legal advice — but it is the wording that made this an easy call.

**2. The lockout risk is documented, not folklore.** Anthropic rotates the refresh token on
every refresh and the spent one dies server-side. claude-unlimited's own source carries the
comment; four open Claude Code issues (#94464, #88947, #80085, #76561) are that bug; and
CodexBar #1161 is a third-party post-mortem where a menu-bar app refreshing Claude Code's
token forced its user to log in daily. archeus's standing read-only policy is correct and
this branch does not weaken it.

**3. The clever-looking alternatives do not deliver mid-session rotation anyway.**
`CLAUDE_CODE_OAUTH_TOKEN` (a one-year token from `claude setup-token`) is fixed for the whole
session — the docs say to restart to replace it. `apiKeyHelper` *is* re-invoked mid-session
(TTL, and on a 401/403), but it copies its output into `x-api-key` as well as the bearer and
Anthropic rejects an `sk-ant-oat…` token there; the known workaround is a proxy to strip that
header, which lands back on (1).

So: **no proxy, no token store, no refresh.** Rotation happens where archeus already decides
which account a process starts under.

---

## What was built

`claude_sessions/rotate.py` — the whole policy, ~230 lines, no I/O of its own.

| | |
|---|---|
| `mode()` | `off` \| `ask` \| `auto`, from `settings['rotate_mode']`. Aliases (`semi`, `full`, `never`, …) are mapped, not rejected: the settings file is hand-editable. |
| `threshold()` | `settings['rotate_threshold']`, default 98.0, clamped to 50-100 **on read**. |
| `spent(cfgdir)` | past the threshold, or refused for a plan window. |
| `elect(current)` | sticky — the account in hand keeps the work until it is spent. |
| `note` / `state` / `recent` | one `events.record('rotate', …)`, and the dict the GUI renders. |

**Two thresholds, on purpose.** `quota.LIMIT_PCT` (100) still decides whether an account may
be *spent*; `rotate.threshold()` (98) decides whether it is *chosen*. Moving the block
threshold would have refused work on an account with 1% left, and `test_quota.py:64` (99%
does not block) is unchanged and still passes.

**Three modes, differing in exactly one thing: who opens the window.** `ask` and `auto` elect
the same account for new work — starting the next process somewhere else is invisible.
Opening a terminal is not, so only `auto` does that by itself.

### Where it takes effect

- **archeus's own `claude -p` calls** — via `quota.preflight`, which all five wrappers
  already call. Two edits inside `quota.py`: `headroom()` skips an account the user took out
  of the rotation (so it is invisible to the picker as well as to the automatic switch), and
  the `auto` branch prefers a candidate under the switch threshold. `_apply` is the one place
  an account actually changes, so it is the one place that records the event.
- **Session launches** — `main.build_launch_command` elects when nothing names an account; an
  explicit `cfgdir` always wins, because picking one in the launch window is a decision. The
  GUI's launch window gained an `auto — most headroom` chip, resolved client-side (the
  sentinel never travels: `/api/launch` has always taken a config dir).
- **A live session that runs out** — the quota strip says so and offers **Continue on `<next>`**,
  which posts the existing `/api/inject/launch` with `target_cfgdir` set to the elected
  account. In `auto` mode it fires by itself, once per (project, target) per page load.

### Surfaces

- GUI: a rotation card on the Accounts page — mode, threshold, per-account opt-out, which
  account is live, which is next, recent switches. It is also the first UI `headless_quota`
  has ever had; it was a real setting with no control on either surface.
- TUI: `Accounts → Rotation`, same four things, and each login row now shows its headroom.
- One new route, `GET /api/rotate/state`. No POST twin: the policy is three declared settings
  so `/api/settings` already takes them (`gui._SETTING_KEYS` is derived from
  `_DEFAULT_SETTINGS`), and the transition is the hand-off endpoint that already existed.

---

## A live bug found on the way, and fixed

`quota._LIMIT_RE` shipped as `re.compile(r'<BS>429<BS>')` — **two literal backspace bytes**
(0x08) where `\b` had been meant. A regex that can never match anything, so that half of the
limit guard had been dead for its entire life. It went unnoticed because every 429 the suite
asserts on also carries `too many requests` or `rate_limit`, and a *marker* caught it.

The obvious repair is also wrong: `\b429\b` matches `wrote 429 lines to quota.py`, which
`test_the_markers_do_not_match_the_models_own_output` explicitly forbids. It now matches the
shape a status code actually arrives in — `"apiErrorStatus":429`, `status: 429`, `code=429` —
which a sentence about a file never looks like.
`test_rotate.py::test_a_bare_429_is_read_as_a_status_not_as_a_number_in_prose` is the gate.

Related and **not** a bug: `quota.is_limit_error` already matches the real refusal
(`You've hit your session limit · resets 2:30am (Europe/Rome)`), and
`test_quota.py:309` already asserts it. Constraint 2 of the track prompt needed no work.

---

## What does not work, stated plainly

- **A running session cannot change account.** Claude Code reads `CLAUDE_CONFIG_DIR` once. The
  successor session is a new terminal window; archeus cannot close the old one.
- **The successor gets a written-out transcript, not the live conversation.** It reads
  `.archeus/injected-context.md` — the existing hand-off. See the experiment below.
- **Codex and pi are not rotated.** Their windows are not Anthropic's and there is no headroom
  figure to compare. Provider-routed sessions are deliberately left alone.
- **Freshness is the usage poller's, 300 s.** The statusline payload already carries
  `rate_limits.five_hour.used_percentage` per turn, for free, for the live session's own
  account — a strictly better signal. Not wired up here because `statusline.py` is outside
  this track's fence and it runs on every turn. Worth a follow-up.

### One experiment left for whoever picks this up

`claude --resume <absolute .jsonl path>` is documented, and so is `CLAUDE_CONFIG_DIR`; the
*combination* is not. If account B can resume account A's transcript by absolute path, the
successor session keeps the real conversation instead of a written-out file — a one-argv-line
change to `api_inject_launch`. Ten minutes to test, and it costs nothing if it fails.

---

## Out-of-fence edits (two lines, both agreed with the user first)

- `config.py` — three `_DEFAULT_SETTINGS` entries beside `headless_quota`. Required: `gui.
  _SETTING_KEYS` is derived from that dict, so this is what makes `/api/settings` accept the
  keys with no handler. Clamping is done in `rotate.py` on read, not in `gui.py`.
- `main.py:1028` — the TUI launch elects its account.
- `docs/api.md` was regenerated by `tools/gen_api_docs.py` (a gate fails otherwise).

Nothing else outside the fence. `CHANGELOG.md` untouched; no screenshots re-shot.

---

## Verification

```
py -m pytest -q                  2352 passed, 1 skipped
py -m pytest tests/test_rotate.py tests/test_quota.py -q      42 passed
py tools/smoke_gui.py            FAILURES: none, JS errors: none
py -m ruff check claude_sessions tools                        All checks passed
py -m mkdocs build --strict      clean
```

---

## CHANGELOG lines for the integrator

```markdown
### Added

- **Automatic account rotation.** When the account in use fills its 5-hour or weekly
  window, the next one with headroom takes over — archeus's own Claude calls, scheduled
  loops and new sessions all start on it. Three modes (Accounts → Account rotation): off,
  semi-automatic (the default — new work moves by itself, a session you are in is offered
  the move) and fully automatic (the successor session opens on its own), plus a switch-away
  threshold and a per-login opt-out. Every switch is recorded in the Logs.
  It rotates by launching the unmodified `claude` binary under each account's own
  `CLAUDE_CONFIG_DIR` and never reads, stores or refreshes a credential, so it cannot log an
  account out of Claude Code.

### Fixed

- **Half of the rate-limit guard had never worked.** `quota`'s 429 pattern contained two
  literal backspace bytes where `\b` had been meant, so it could never match; a 429 was only
  ever caught when the text happened to carry another marker as well. It now matches a status
  code (`"apiErrorStatus":429`, `status: 429`) without matching a number in prose.
```
