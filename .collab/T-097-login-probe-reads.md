# T-097 · What the login probe reads in an account home (code-only analysis)

By Qwen (pi, spark/qwen3.8-flash-next) · 2026-10-15 · corrected 2026-10-16 per
`reviews/T-097-analysis.md` (3 findings) and r2-corrected 2026-10-19 per
`reviews/T-097-analysis.r2.md` (1 finding; see the correction sections at the end) · per card
T-097. Source read only, in D:/archeus-p20-i. No file under any account home, `~/.claude` or any credential store was
opened, listed or printed; no command touched user files; no network; no source changed.
All statements below are from the repository code only, cited file:line.

## The probe chain

- `archeus/harnesses/calls.py:79-82` — `ClaudeCodeCaller.authenticate`:
  `ok = bool(usage._creds(account.home_ref))`, returns
  `AuthStatus(ok, '' if ok else 'no Claude login in %s' % account.home_ref)`.
  Docstring: "Cheap, no inference". No subprocess, no network in this method.
- `archeus/harnesses/claude_code/adapter.py:115-118` — `ClaudeCodeAdapter.authenticate`:
  the byte-same implementation on the registry adapter. `Resources.probe`
  (`archeus/core/application/resources.py:606-620`) takes the **first** adapter of the
  harness id that has `authenticate`, so exactly one of the two runs per probe.
- `claude_sessions/usage.py:45-54` — `_creds(cfgdir)`:
  - Opens **one file**: `os.path.join(cfgdir or _c.config_dir, '.credentials.json')`
    (usage.py:50) in `'r'` mode only (usage.py:51). With the probe, `cfgdir` is the
    account's `home_ref`; when that is `None`, `config.config_dir` (the active Claude
    config dir) is the fallback.
  - Reads it whole with `json.load`, returns the `claudeAiOauth` block or `{}`
    (usage.py:52-53). Any error — missing file, bad JSON, permission denied — returns
    `{}` (usage.py:53-54); the probe then says "no Claude login in <home>".
  - Docstring (usage.py:46-48) states archeus NEVER writes this file; verified: no
    write, `json.dump`, or `open(..., 'w')` on it anywhere — the only reference to the
    filename outside `_creds` is the same assertion in `claude_sessions/harnesses.py:656`,
    and the only `open(` in usage.py is the `'r'` one at usage.py:51.

## What the probe itself reads

The probe consumes only the **truthiness** of the `claudeAiOauth` dict
(calls.py:81 / adapter.py:117): non-empty → ok. It reads no named field and its result
carries no credential value — the only string it can produce is
`'no Claude login in %s' % account.home_ref` (a path, not a secret)
(calls.py:82 / adapter.py:118).

Sibling readers of the same block, for completeness (they read fields, the probe does not):

| Field(s) read | Function | File:line |
|---|---|---|
| `accessToken` | `_read_token` | claude_sessions/usage.py:57-58 |
| `expiresAt` | `_token_expired` | claude_sessions/usage.py:61-68 |
| `account.email_address`/`emailAddress`/`email` (+ top-level) | `_account_email` | claude_sessions/usage.py:71-80 |
| `subscriptionType`, `rateLimitTier` | `account_meta` | claude_sessions/usage.py:83-87 |

## Are any values copied, logged, cached, written or sent?

- **Written to disk: no.** `_creds` is read-only (usage.py:51); no write-back path
  exists for `.credentials.json` anywhere in `archeus/`, `claude_sessions/` or `tools/`
  (grep for the filename and `json.dump`/`open(...'w')`). The docstring's reason
  (token-rotation write-back could log the account out) is backed by the absence of any
  writer.
- **Persisted in Core's DB: no credential value.** `Resources.probe` stores only
  `{'ok': bool, 'detail': str}`; the register/enable commands (register_account
  resources.py:57, 82-84; set_account_enabled resources.py:88, 95-97) turn that into an
  `auth_ok`/`auth_failed` lifecycle event whose `reason` is the detail string — at
  worst the home path. One edge: on an adapter *exception* the reason becomes
  `'%s: %s' % (type(e).__name__, e)` (resources.py:615-616); `_creds` swallows its own
  exceptions, so this path yields exception text, not file contents.
- **Cached: in-process only, and never the token.** The usage poller caches per-account
  state in the module-level dict `_acct_state` (usage.py:41): `name`, `status`, plan/
  tier (`account_meta`, usage.py:169), `email` (`_account_email`, usage.py:170-171), the
  usage-endpoint JSON `data`, derived `spend`, and timestamps (usage.py:165-178).
  `accessToken` is **not** stored there — `_read_token` hands it straight to
  `fetch_usage`. **Core does reach this cache — corrected 2026-10-16 (finding 1); the
  earlier "Core never reads this cache" was wrong.** The grep that mislead is real
  (`_acct_state`/`account_meta`/`_account_email` do not appear in `archeus/`), but Core
  goes through the accessor instead of naming the dict: `archeus/core/routing/usage.py:63-64`
  — `LegacyUsageFeed.read`, the product default at `archeus/core/runtime.py:116` — calls
  `usage.windows_snapshot(os.path.expanduser(account['home_ref']), poll=True)`, and
  `windows_snapshot` (usage.py:241-259) reads that cache directly: `st.get('data')`,
  `st.get('fetched_at')`, `st.get('status')` out of `_acct_state` (usage.py:253-259).
  `poll=True` also calls `_ensure_started()` (usage.py:249-250 → 213-221), which starts the
  daemon poller thread that does the credential reads — for **every** Claude Code home at
  once (`_targets()` → `all_config_dirs()`, usage.py:104-116, config.py:875-889). Its
  caller is allocation governance, not login: `archeus/core/execution/manager.py:718`
  (`_ceilings`, §12.2) asks for each account with a live execution and feeds the answer to
  `resources.observe` (resources.py:160-178), which persists `UsageSnapshot` rows — window
  percentages, reset times, source, observed_at; no credential field. So this is an
  **indirect Core path**: a cache read plus a poller start-up. It is not an authentication:
  it never produces `auth_ok`/`auth_failed` and never touches the probe's verdict (see
  "Which code paths run the read"). What Core consumes is percentages and a status string,
  never a field of `.credentials.json`.
- **Logged: no *explicit* credential logging in the inspected code** (narrowed
  2026-10-16, finding 3 — the earlier blanket "no credential value" claimed more than the
  code proves). The only logging on this path is `_c.log.exception('usage fetch failed')`
  (usage.py:163), inside `_poll_account`'s bare `except Exception` (usage.py:162-164): it
  writes whatever traceback the code above it raised, with **no redaction step in front of
  it**. What the inspected code supports: nothing in it puts a credential field into a log
  message — the token is set only in the request header (usage.py:129-133) and never in the
  URL (`USAGE_URL` is a module constant, usage.py:18). What it does **not** support is a
  guarantee about the exception *text*: header placement cannot rule out a library exception
  whose message echoes request data. Whether a `urllib`/`ssl` exception can ever carry a
  header value is **not verified** here — it is a stdlib-internals question, outside this
  card's read-only source scope, and the claim stops at "no explicit credential logging".
- **Sent anywhere: the access token over the network in one place; three more
  credential-file fields into one local GUI response**
  (split 2026-10-16, finding 2 — "one place" conflated two different things; **r2
  correction 2026-10-19**: `email`, `plan` and `tier` **are** fields of
  `.credentials.json`, copied by `_account_email`/`account_meta` — the earlier "not a
  field of the file" was wrong, and "the only place a field … leaves the process" holds
  only of the access token).
  - **The credential itself**: `fetch_usage` sends `accessToken` as the
    `Authorization: Bearer` header of a GET to the constant
    `USAGE_URL = 'https://api.anthropic.com/api/oauth/usage'` (usage.py:18, 128-136).
    That is the usage poller — `authenticate`/`_creds` make no network call — and it is the
    only place the **access token** leaves the process; no field of the credential store
    reaches the network anywhere else in the inspected code.
  - **Credential-file fields, copied and *returned*** (r2: these are fields **of the
    file itself**, not merely "derived"): `email` — `_account_email` (usage.py:71-80)
    reads `account.email_address`/`emailAddress`/`email` out of the `claudeAiOauth` block
    (`853f63f:claude_sessions/usage.py:73-87`) — and `plan`/`tier` — `account_meta`
    (usage.py:83-87) reads `subscriptionType`, `rateLimitTier` from the same block. The
    poller stores those values in `_acct_state` (usage.py:169-171), and
    `api_usage_plan` (`claude_sessions/gui_api.py:1128`, route table entry
    gui_api.py:4638) answers with them per account — `'email': st.get('email', '')`
    (gui_api.py:1149), `'plan': st.get('plan', '')`, `'tier': st.get('tier', '')`
    (gui_api.py:1154), with `status`, `spend` and the window rows — as the
    `{'accounts': out}` response body (gui_api.py:1166). That is served by the GUI's own
    `ThreadingHTTPServer` on 127.0.0.1 (gui.py:3, 1005), so it goes to the local GUI page,
    not to Anthropic: account metadata copied out of the credential file, not a bearer
    credential, but still file-sourced values leaving the process (r2).
  The probe is on neither leg.
- **Copied into child environments: no.** `_env`/`account_env` pass directory paths and
  pop `ANTHROPIC_API_KEY` from the child env (calls.py:22-27, config.py:891-906); no
  credential file content is read into an env or argv.

## Which code paths run the read

The probe (`authenticate` → `_creds`) runs **only on account management**, never per call:

- `POST register_account` — probe before the registering command (archeus/api/routes.py:510).
- `set_account_state` enabling an account (routes.py:520, probe only when `enabled`).
- Both via `Resources.probe` (resources.py:606-620); grep for `.probe(`/`authenticate(`
  finds no other caller in `archeus/`. `ClaudeCodeCaller.call` (calls.py:96-127) never
  calls `authenticate` — an own call runs `claude -p` via `llmcall.run_headless` and it
  is the Claude CLI process itself, not archeus code, that then reads its own config dir
  (selected by `CLAUDE_CONFIG_DIR`, config.py:891-906).

Other code paths that read the same file through the same `_creds` (relevant because the
card asks about the read, not only the probe endpoint):

- Usage poller background thread: `_poll_account` → `fetch_usage`/`account_meta`/
  `_account_email` (usage.py:161-180, `_background` usage.py:189-207), fed by
  `all_config_dirs()` — deliberately **only Claude Code homes** (config.py:875-889).
- **What can start that thread from Core** (finding 1, 2026-10-16):
  `archeus/core/routing/usage.py:63-64` → `windows_snapshot(..., poll=True)` →
  `_ensure_started()` (usage.py:249-250, 213-221), reached from
  `archeus/core/execution/manager.py:718` (`_ceilings`) while any execution is
  STARTING/RUNNING/PAUSING on an account with a `home_ref`. So the file read is **not**
  confined to `claude_sessions/` being open: a Core allocation-ceiling read can be the
  first thing that opens `.credentials.json`, and it does so for every Claude Code home.
  That is still not the probe — `authenticate` → `_creds` remains register/enable-only —
  and the Core path consumes window percentages and a status string only.
- **What can start that thread from Core** (finding 1, 2026-10-16):
  `archeus/core/routing/usage.py:63-64` → `windows_snapshot(..., poll=True)` →
  `_ensure_started()` (usage.py:249-250, 213-221), reached from
  `archeus/core/execution/manager.py:718` (`_ceilings`) while any execution is
  STARTING/RUNNING/PAUSING on an account with a `home_ref`. So the file read is **not**
  confined to `claude_sessions/` being open: a Core allocation-ceiling read can be the
  first thing that opens `.credentials.json`, and it does so for every Claude Code home.
  That is still not the probe — `authenticate` → `_creds` remains register/enable-only —
  and the Core path consumes window percentages and a status string only.
- `harnesses.auth_state` — the accounts-list "signed in?" column (harnesses.py:650-668):
  `_read_token` + `_token_expired`, "a file read and not a request" (harnesses.py:655-657).
- `quota.worst_window`/`reason` — cache reads only (quota.py:260-288, 293-313); but
  `quota.headroom` calls `usage._read_token`/`_token_expired` per account (quota.py:338),
  so the account-switch picker touches the file too.
- `why_not` on the router's health list (calls.py:90-92 → quota.reason) stays on the
  cached path above.

## Does this change D7 (Core stores no API key)?

**No — D7 stands.** The probe's relationship to the credential store is read-only and
boolean: `_creds` parses the file and hands back the `claudeAiOauth` block; the probe
keeps only its truthiness, and the value that reaches Core's DB is `ok` plus a
path-bearing detail string (resources.py:612-617, resources.py:82-84). Reading is not
storing, and the two flags the card asks for come back clear: **no write** (no writer
exists for the file; repo-wide grep) and **no cache of the token** (`_acct_state` holds
status/plan/email/usage-data only, usage.py:165-178; token exists transiently in
`fetch_usage`'s header, usage.py:130). The single network send of `accessToken` is the
usage poller to Anthropic's own usage endpoint — consistent with D7, which is about
*Core storing* a key, not about the Claude-Code-side OAuth flow the poller mirrors. The
Core path added by correction 1 (finding 1) does not move this either: `LegacyUsageFeed.read`
reads cached percentages and status, starts the poller, and stores `UsageSnapshot`
percentages/reset times (resources.py:174-176) — no credential field reaches Core's DB, and
nothing here writes to the credential store. The
Core path added by correction 1 (finding 1) does not move this either: `LegacyUsageFeed.read`
reads cached percentages and status, starts the poller, and stores `UsageSnapshot`
percentages/reset times (resources.py:174-176) — no credential field reaches Core's DB, and
nothing here writes to the credential store.

Residual note (not a flag, just exactness): the poller cache holds the account **email**
in process memory (usage.py:170-171); it is returned — not merely held — in the local
GUI's `/api/usage/plan` response body (gui_api.py:1149, 1154, 1166; route table 4638), and
never persisted by Core. If a future card ever persists `_acct_state`, that
email would become stored account data — worth one line in slice K's review.

## Correction 2026-10-16 (Qwen) — `reviews/T-097-analysis.md`, 3 findings

Codex's aimed review returned CHANGES on three claims. Each was re-checked against the
candidate source in `D:/archeus-p20-i` before being changed, and each is fixed **in place**
at the offending sentence, so the claim reads corrected where it is used:

1. **"Core never reads this cache" — wrong; withdrawn** ("Cached" bullet, new bullet in
   "Which code paths run the read"). Core reaches `_acct_state` through the accessor:
   `archeus/core/routing/usage.py:63-64` (`LegacyUsageFeed.read`, default from
   `archeus/core/runtime.py:116`) calls `usage.windows_snapshot(home_ref, poll=True)`, which
   reads the cache (usage.py:253-259) and `poll=True` starts the credential-reading poller
   via `_ensure_started()` (usage.py:249-250, 213-221); the caller is
   `manager._ceilings` (`archeus/core/execution/manager.py:718`). The original grep was
   literally right — those three symbols really are absent from `archeus/` — and the
   inference drawn from it was not: only `windows_snapshot` appears there
   (routing/usage.py:55, 63), and that is the cache's read entry point. Distinguished from
   register/enable authentication, which stays the only path that produces an auth verdict.
   D7 is unchanged, as the review itself says.
2. **"Sent anywhere: one place" — too coarse; split** ("Sent anywhere" bullet). The token
   goes to one place (Bearer header → Anthropic's usage endpoint, usage.py:128-136);
   credential-derived `email`/`plan`/`tier`/`spend` are additionally copied into
   `_acct_state` (usage.py:170-172) and returned in the local GUI's `/api/usage/plan`
   response body (`claude_sessions/gui_api.py:1128, 1149, 1154, 1166`; route table 4638;
   server on 127.0.0.1, gui.py:3, 1005).
3. **"Logged: no credential value" — stronger than the evidence; narrowed** ("Logged"
   bullet). `_c.log.exception` (usage.py:163) sits in a bare `except Exception` with no
   redaction, so the claim is now "no explicit credential logging in the inspected code",
   and whether a stdlib exception could echo a header is recorded as **not verified**
   instead of being ruled out by header placement.

Nothing else in the note changed, and no conclusion moved: the probe still reads one file
for one boolean, no credential value is written or cached, D7 stands. Still read-only
throughout: no file under any account home, `~/.claude` or any credential store was opened,
listed or printed; no command touched user files; no network; no code or test change.

## Correction r2 2026-10-19 (Qwen) — `reviews/T-097-analysis.r2.md`, 1 finding

Codex's aimed re-review returned CHANGES on finding 2 alone ("Findings 1 and 3 answered
accurately"). The error: the corrected "Sent anywhere" bullet still called the GUI-returned
`email`/`plan`/`tier` "derived account metadata, **not a field of the file**", and still
called the Bearer header "the only place a field of `.credentials.json` leaves the
process". Both are wrong in the same direction. `_account_email` (usage.py:71-80) and
`account_meta` (usage.py:83-87) copy `email`, `plan` and `tier` **from the
`claudeAiOauth` block of the file itself** (`853f63f:claude_sessions/usage.py:73-87`), and
`api_usage_plan` returns them (`gui_api.py:1149, 1154`). Fixed **in place**, as the review
required: "not a field of the file" removed, the three values named as credential-file
fields with their reader citations, and the exclusivity claim narrowed to the access token
— `accessToken` is the only credential-store value that reaches the network (Bearer header,
usage.py:129-133); the file-sourced `email`/`plan`/`tier` leave the process only through
the local 127.0.0.1 GUI response body. While re-checking citations for this round I also
corrected three off-by-two/off-by-one line spans in the sibling-readers table
(`_token_expired` 61-68, `_account_email` 71-80, `account_meta` 83-87) and the
`_acct_state` write lines (usage.py:169-171, was "170-172") — all re-read against the
candidate at `853f63f` in `D:/archeus-p20-i` (line-checked with read-only `grep -n`/`awk`).
No conclusion moves: the probe still reads one file for one boolean, no credential value
is written and no token is cached, and **D7 (Core stores no API key) stands** — the file
reads that copy email/plan/tier are the poller's, and Core still persists only
`UsageSnapshot` percentages/reset times (resources.py:174-176), no credential field.

Still read-only throughout: no file under any account home, `~/.claude` or any credential
store was opened, listed or printed; no command touched user files; no network; no code or
test change.

— Qwen
