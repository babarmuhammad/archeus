# T-110 (recovered)

Qwen, 2026-10-19. Recovered from note write and subsequent citation corrections. Code examined at `b73f875` in `D:/archeus-p20-mcp`; canonical documents read in `D:/Claude`. Analysis only: no tests, processes, native/ACL operations or web fetch.

**O7 decision exists; required policy remains unspecified and unbuilt.** Decision lives outside `docs/architecture/`, in `PV20-S1-GATE-2026-10-08.md` §7, heading at `:128`, decision at `:130`, bullets at `:132–141`:

> - An isolation-establishment failure (`SpawnFailed`) is an infrastructure/isolation failure, not a failure of the user's task.
> - It is therefore NOT charged against the task/execution outcome as task failure.
> - Retry is permitted only under a bounded backoff policy.
> - A breaker must prevent indefinite repeated attempts when isolation establishment is unhealthy.
> - After the retry/breaker policy is exhausted, the condition is surfaced as an infrastructure/isolation failure requiring recovery/reconciliation.
> - There is NEVER an unisolated fallback.
> - There is NEVER a bypass of A4/isolation to make the execution run.
> - The failure state must remain deterministically reconcilable by Core across restart.

Placement specified in same gate:

- §7.3, `:157–164`: “The backoff/breaker **policy mechanism** consumes those facts on the **dispatch side (P11-owned, production dispatch E-gated)** and is **not** a new S1 component.” Assigning mechanism into S1 would change scope and re-enter gate.
- §7.5 item 10, corrected citation `:181–183`: “**No permission to modify production dispatch**: the retry/breaker policy operates only where dispatch already exists; S1 dispatches nothing, production dispatch remains unauthorized, and enabling it stays E's.”

Earlier documents defer decision to P11:

- `docs/architecture/p20-design-gate.md:371`, `:1250–1262`, `:1420–1429`, `:2770`: uncharged `binding` spawn failure re-dispatches every tick; charging, backoff/breaker or routing away were alternatives. “40 executions in 40 ticks” appears at `:1255–1256`, `:1425–1426`.
- `docs/architecture/p11-design-gate.md:1018–1022`: “O7 stays P11's”; not decided there. A1 amendment `:1030–1031`: structural workspace impossibility refused before dispatch; “**Only a transient workspace failure is O7's.**”
- `docs/architecture/pv20-execution-isolation-design.md:309–312`, `:400`, `:650`, `:715`, `:894`; `docs/architecture/decisions/ADR-0053.md:66`, `:178–179`, `:220`, `:430`: same delegation and invariant that O7 never bypasses isolation.
- No canonical conflict found. Gate §7.2, corrected citation `:152–155`: “uncharged is a legal value of that delegation”.

**Decided versus open**

| Attribute | Final note’s finding |
|---|---|
| Charging | Decided: isolation-establishment failure uncharged (`PV20-S1-GATE-2026-10-08.md:134`). |
| Location | Coarse placement decided: dispatch side, P11-owned, E-gated, outside S1 (`:157–162`). Exact subject/key and implementation location open. |
| Threshold | Open. No O7 count specified. |
| Window | Open. No O7 interval specified. |
| Backoff | Bounded policy required; sequence, floor, cap and timer owner open. |
| Reset | Restart reconcilability required (`:141`); human recovery versus automatic probe, half-open path and clearing authority open. |
| Visibility | Exhaustion must surface as infrastructure/isolation failure requiring recovery/reconciliation (`:137–138`); concrete API/TUI/mission/Core surface open. |

Note lists nine owner questions: breaker key; threshold; window; backoff shape/timer; recovery trigger; visibility; whether non-isolated permanent `Popen` failure belongs to O7; router versus manager blocking point; and T-106 authority to modify dispatch code while production switch remains off. Minimum first-cut decisions: key, threshold/window, recovery, surface and permanent-`Popen` scope.

**Existing mechanisms that could carry policy**

- **Execution/account-health breaker:** `archeus/core/domain/states.py:285–303`; `archeus/core/application/executions.py:825–860`, constants `:799–801`; driven from `archeus/core/execution/manager.py:130–132`. Uses `AVAILABLE/CONSTRAINED → DEGRADED → OPEN`, storm count 5/600 seconds, persistence 2, cooldown 300 seconds. Right shape, wrong key: counts only `ENDED_ERROR` with `resource` or `auth` (`executions.py:838–843`), never ABANDONED refusal. Expanding counter changes canonical contract (`p11-design-gate.md:452–467`); copying machine for harness/isolation subject cleaner reading. Harness-owned account lacks registered-account breaker (`p11-design-gate.md:951`).
- **Harness state:** `archeus/core/domain/states.py:395`: `AVAILABLE`, `MISSING`, `MISCONFIGURED`, discovery-driven. Natural key for harness unable to spawn, but no failure-driven trip/reset transitions. Router uses harness snapshot fields (`archeus/core/routing/router.py:100–110`, `:217`, `:272`).
- **Pairing breaker:** `archeus/api/auth.py:198–236`, limit 10/60 seconds (`:209–210`); HTTP mapping `routes.py:274–276`. Sliding window/timed unlock pattern, but `_fails` and `_locked_until` in memory (`auth.py:214–215`): verbatim copy fails O7 restart-reconcilability requirement.
- **P14 automation loop guard:** `archeus/core/application/automations.py:269–279`; `archeus/core/automation/matcher.py:26–27`, 3/3600 seconds; `states.py:263`, `ENABLED → SUSPENDED`; TUI `cli/tui/_tables.py:364`. Suspends until user re-enables (`automations.py:276–278`); useful manual-recovery pattern, different subject and counter.
- **Existing mission halt:** `BLOCKING = ('path_too_long',)` (`executions.py:40–42`), honored at `:211–212`, `_block` at `:545–548`. Adding stop reason could halt repeat refusal, uncharged and visible. Answers exhaustion clause only; supplies no bounded retries.

**Permanent spawn-failure dispatch path at `b73f875`**

Entry: `ExecLoop._run → manager.tick()` (`archeus/core/runtime.py:286–295`, `EXEC_S = 0.05` at `:260`) → `_step` (`manager.py:170–188`) → `_first` (`:192–203`) → `_spawn` (`:205–348`).

1. **Pre-child write failure, already bounded:** directory/marker/prompt write raises `OSError` → `SpawnWriteFailed` (`archeus/harnesses/base.py:341–363`, class `:267–271`) → manager refuses charged `workspace` (`manager.py:324–331`) → charged attempts reach `max_attempts`, task FAILED (`executions.py:484–499`, `:69–72`). No indefinite loop.
2. **Non-isolated permanent `Popen` failure, live loop:** `proc.spawn_detached` returns `(None, err)` (`base.py:390–392`) → `_refuse` (`:393–396`) writes ended tombstone, raises `SpawnFailed` (`:400–408`) → manager catches `SpawnFailed`/`AlreadySpawned`, refuses uncharged `binding`, releases isolation (`manager.py:332–341`).
   - `binding ∈ UNCHARGED` (`executions.py:38–39`); refusal writes `charged: False` (`:195`), fires `spawn_failed`, execution becomes ABANDONED (`:198–200`).
   - `_respond` fires `execution_failed_retry` unconditionally when uncharged (`:480–483`). **No `max_attempts` check**; bound exists only in charged branch (`:490–499`). Task returns READY.
   - `binding` absent from `BLOCKING` (`:40–42`), mission stays dispatchable. Engine re-dispatches (`runtime.py:158–167`, `archeus/core/engine.py:272–280`, `archeus/core/application/work.py:315–330`).
   - Every pass reports work (`manager.py:116–141`), so no ExecLoop idle wait (`runtime.py:293–295`). Repeated rows, events, execution directories, markers and tombstones.
   - Account breaker cannot count ABANDONED refusal (`executions.py:838–843`). Review measured **63 uncharged ABANDONED executions in 4 seconds** (`reviews/T-102-c91d4f1.claude.md`, “Ran”); Qwen quoted result, did not remeasure.
3. **Actual isolation-establishment failure, O7’s scope, latent:** private-directory/environment failure (`base.py:364–376`) or `IsolationUnavailable` converted to `SpawnFailed` (`archeus/node/isolation.py:1567–1602`) → `LocalNode.spawn` records `isolation_failed` before rethrow (`archeus/node/local.py:164–172`, `isolation.py:783–799`) → same uncharged `binding` refusal (`manager.py:332–341`). Production path disabled: `PRODUCTION_DISPATCH_ENABLED = False` (`isolation.py:86–90`, `requested()` `:685–696`); `default_plan` deliberately unsatisfiable (`:1524–1534`).

No `backoff` found in execution, harness or node directories at examined commit. `manager.py:336–337` refers to bounded retry policy that does not yet exist; review agrees: “No such mechanism exists yet.”

# T-097 (recovered)

Qwen. Original note dated 2026-10-15, corrected 2026-10-16; first supplied session verified correction against candidate `853f63f` in `D:/archeus-p20-i`. Second supplied session applied r2 correction dated 2026-10-19. Source inspection only: no actual account-home or credential-store files opened, listed or printed; no network or tests.

**Login probe opens one file and consumes one boolean.**

- `ClaudeCodeCaller.authenticate` (`archeus/harnesses/calls.py:79–82`) evaluates `bool(usage._creds(account.home_ref))`, returns `AuthStatus(ok, '' if ok else 'no Claude login in %s' % account.home_ref)`. No subprocess or network.
- Registry adapter has identical implementation (`archeus/harnesses/claude_code/adapter.py:115–118`). `Resources.probe` selects first matching adapter with `authenticate`, so only one runs per probe (`archeus/core/application/resources.py:606–620`).
- `_creds` (`claude_sessions/usage.py:45–54`) opens `os.path.join(cfgdir or _c.config_dir, '.credentials.json')` (`:50`) in read mode (`:51`), parses whole file with `json.load`, returns `claudeAiOauth` block or `{}` (`:52–53`). Missing file, bad JSON, permissions or other errors return `{}` (`:53–54`). Probe uses account `home_ref`; `None` falls back to active Claude config directory.
- Probe reads **no named field**: nonempty OAuth dictionary means `ok`. Returned result contains boolean and empty string or home-path detail, no credential value (`calls.py:81–82`, `adapter.py:117–118`).

Sibling readers inspect fields from same block:

| Field | Reader | Corrected citation |
|---|---|---|
| `accessToken` | `_read_token` | `claude_sessions/usage.py:57–58` |
| `expiresAt` | `_token_expired` | `claude_sessions/usage.py:61–68` |
| `account.email_address` / `emailAddress` / `email`, plus top-level variants | `_account_email` | `claude_sessions/usage.py:71–80` |
| `subscriptionType`, `rateLimitTier` | `account_meta` | `claude_sessions/usage.py:83–87` |

**Copies, storage, logs and sends**

- **Credential-file writes:** none found. `_creds` read-only (`usage.py:51`); inspected `archeus/`, `claude_sessions/`, `tools/` contain no write-back path. Docstring says archeus never writes file (`:46–48`); same assertion at `claude_sessions/harnesses.py:656`.
- **Probe persistence:** Core stores `{'ok': bool, 'detail': str}` and `auth_ok`/`auth_failed` event with detail as reason (`resources.py:57`, `:82–84`, `:88`, `:95–97`, `:612–617`). Adapter exception can produce `'%s: %s' % (type(e).__name__, e)` (`:615–616`); `_creds` swallows its own exceptions.
- **Cache:** poller’s in-process `_acct_state` (`usage.py:41`, `:165–178`) holds name/status, plan/tier (`:169`), email (`:170–171`), endpoint response data, derived spend and timestamps. **No token cached there.** Token transiently passed into `fetch_usage`.
- **Core indirectly reaches cache and can start poller:** `LegacyUsageFeed.read` (`archeus/core/routing/usage.py:63–64`), default at `archeus/core/runtime.py:116`, calls `windows_snapshot(..., poll=True)`. Snapshot reads cached data/fetched-at/status (`usage.py:241–259`, especially `:253–259`); `poll=True` starts daemon via `_ensure_started` (`:249–250 → :213–221`). Poller targets every Claude Code home (`usage.py:104–116`, `claude_sessions/config.py:875–889`). Caller `_ceilings` (`archeus/core/execution/manager.py:718`) serves live executions; `resources.observe` persists `UsageSnapshot` percentages/reset times/source/observed-at, no credential field (`resources.py:160–178`, `:174–176`).
- **Logging:** supported claim is **“no explicit credential logging in the inspected code.”** `_poll_account` catches `Exception` and calls unredacted `_c.log.exception('usage fetch failed')` (`usage.py:162–164`, log at `:163`). Token explicitly placed in header, not constant URL (`:129–133`, `:18`). Whether library exception text can echo header value: **[not in transcript]**; note explicitly marks unverified.
- **Network:** `fetch_usage` sends `accessToken` in `Authorization: Bearer` header to `https://api.anthropic.com/api/oauth/usage` (`usage.py:18`, `:128–136`, specifically `:129–133`). This is poller path; `authenticate` and `_creds` make no network call. In inspected code, access token is only credential-store value reaching network.
- **Local GUI response:** email, plan and tier **are copied credential-file fields**, not merely derived metadata. `_account_email` and `account_meta` copy from `claudeAiOauth` (`853f63f:claude_sessions/usage.py:73–87`), cache at `usage.py:169–171`; `api_usage_plan` (`claude_sessions/gui_api.py:1128`) returns email (`:1149`), plan/tier (`:1154`), plus status/spend/windows in `{'accounts': out}` (`:1166`), route `/api/usage/plan` (`:4638`). GUI server binds `127.0.0.1` (`claude_sessions/gui.py:3`, `:1005`). These file-sourced metadata values leave process through local GUI response; probe participates in neither send.
- **Child environment/argv:** no credential-file content copied. `_env`/`account_env` pass directory paths and remove `ANTHROPIC_API_KEY` (`calls.py:22–27`, `config.py:891–906`).

**Read-triggering paths**

- Login probe runs on account management: registration (`archeus/api/routes.py:510`) and enabling account (`:520`, only when enabled), through `Resources.probe` (`resources.py:606–620`).
- Per-call `ClaudeCodeCaller.call` never invokes authentication (`calls.py:96–127`). It launches `claude -p` via `llmcall.run_headless`; Claude CLI reads its own config directory selected by `CLAUDE_CONFIG_DIR` (`config.py:891–906`).
- Background usage poller reads via `_poll_account → fetch_usage/account_meta/_account_email` (`usage.py:161–180`, `_background` `:189–207`).
- Core allocation-ceiling path can start poller while execution STARTING/RUNNING/PAUSING on account with `home_ref` (`manager.py:718`, routing `usage.py:63–64`). Thus reads need not wait for legacy GUI: Core can trigger first credential-file reads across all Claude Code homes. This path produces no authentication verdict.
- Accounts-list signed-in column uses `harnesses.auth_state → _read_token/_token_expired` (`claude_sessions/harnesses.py:650–668`), “a file read and not a request” (`:655–657`).
- `quota.worst_window`/`reason` use cache (`claude_sessions/quota.py:260–288`, `:293–313`); switch-picker `quota.headroom` reads token/expiry (`:338`).
- Router health-list `why_not → quota.reason` stays cached (`calls.py:90–92`).

**Corrections incorporated**

2026-10-16 review corrected three claims:

1. “Core never reads this cache” withdrawn: Core uses accessor and can start credential-reading poller.
2. “Sent anywhere: one place” split into bearer-token send and local GUI response.
3. Blanket “no credential value” logging guarantee narrowed to no explicit logging; exception contents unverified.

2026-10-19 r2 fixed remaining error: email/plan/tier **are fields copied from credential file** (`853f63f:claude_sessions/usage.py:73–87`, `gui_api.py:1149–1154`). Removed “not a field of the file”; narrowed “only place a field … leaves the process” to **accessToken**. Corrected sibling-reader and cache-write line spans as shown above. Earlier correction’s broad “no credential value … cached” cannot describe metadata; final finding is **no token cached**, while email/plan/tier are cached and returned locally.

**D7, “Core stores no API key,” still stands.** Probe retains boolean/path detail; no credential-file writer found; no token cache found. Core’s indirect poller/cache path persists only usage snapshots (`resources.py:174–176`), no credential field. Poller’s transient bearer-token use and local metadata response do not establish Core key storage.