# T-087 draft and the native-card authorisations (T-063, T-064, T-068)

Claude (fork), 2026-10-14. Read-only on `D:/archeus-pv20-integration` at `b6ff773` (T-072 candidate round 3: 7685559 + T-083 + T-085/T-086). Nothing was run, edited or committed in code; BOARD.md untouched. FACT = read in the code at b6ff773; UNVERIFIED = not checked.

## Part A. T-087: own calls stop inheriting Core's environment (T-053 P6, second clause)

### What P6 says

`.collab/T-053-origin-transport-contract.md:121-129`, P6: no Archeus-owned process running as the user may, with execution-influenced content, "receive Core's environment, including `ARCHEUS_HOME`, unless it is part of Core". O6 (`:48`, `:51-57`) lists the model calls as deputies: `env=config.account_env(home)` at `harnesses/calls.py:92-96`, `:146-148` (5dfac53 lines).

### Where an own call's environment is built today (FACT, b6ff773)

| Caller | Line | Environment |
|---|---|---|
| `ClaudeCodeCaller.call` | `archeus/harnesses/calls.py:92` | `config.account_env(spec.account.home_ref)`; a no_tools call adds `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` (`:102`, T-086) |
| `PiCaller.call` | `archeus/harnesses/calls.py:160` | `config.account_env(spec.account.home_ref)` |
| `config.account_env` | `claude_sessions/config.py:891-909` | `os.environ.copy()` (`:904`), sets the harness's home variable (`CLAUDE_CONFIG_DIR` / `PI_CODING_AGENT_DIR`), pops `env_pops` (`ANTHROPIC_API_KEY` for Claude, `OPENAI_API_KEY` for Codex, nothing for pi: `claude_sessions/harnesses.py:125`, `:220`, `:338`) |

So an own call receives Core's whole process environment minus one provider key. Since T-081/T-085/T-086 every own call has no tools and (Claude) runs in safe mode, so nothing inside the call can read the environment back out; the remaining exposure is the CLI process itself and anything it spawns, plus the P6 rule as written.

### What reaches the child

- **`ARCHEUS_HOME`**: only when Core's own process has it. No production code sets it in `os.environ` (FACT: the only writer is `base.py:354` for a non-isolated execution child; `tools/check_wheel.py:25` is a tool); the user, the test suite and a developer environment do. When set, it names `run/` (`core.json`, `local-token`) and `archeus.db`.
- **Every other `ARCHEUS_*`** in Core's environment (`ARCHEUS_DEBUG`, `ARCHEUS_FREE`, `ARCHEUS_TUI_*`, `ARCHEUS_RELAUNCH`, `ARCHEUS_UPDATE_TO`, `ARCHEUS_BAT` …), and every `PYTEST_*` when Core runs under pytest.
- **No Core secret travels by environment** (FACT: the local token is a file, `run/local-token`; `api/auth.py`, `core/runtime.py`, `infra/discovery.py` read no token variable).
- **What the child legitimately needs**: the CLI's own variables (PATH, USERPROFILE/APPDATA/TEMP, the harness home variable, proxy and certificate variables, and for pi the key its `models.json` names, e.g. `$SPARK_QWEN_KEY`). Nothing in an own call needs `ARCHEUS_*`: there is no hook (safe mode / `--no-extensions`), and only an execution's hook reads `ARCHEUS_HOME` (`archeus/harnesses/hook.py:131`), which is Core's code in an execution, not an own call.

### Precedent already in the tree

`archeus/node/local.py:607-612` (`run_check`): `env = {k: v for k, v in os.environ.items() if not k.startswith(('PYTEST_', 'ARCHEUS_'))}`, with the comment that `ARCHEUS_HOME` locates `run/` and the hook names carry execution credentials. The same filter is the smallest correct change for own calls.

### Out of this card (recorded, not mapped further)

- Non-isolated execution children get `dict(os.environ)` plus `ARCHEUS_EXECUTION_ID`/`ARCHEUS_HOME` (`base.py:347-354`): the hook needs both, and the hook is Core's (P6 "unless it is part of Core"); the other inherited variables are R4b/E's.
- The isolated path builds its environment from nothing (`base.py:451-474`, T-031) and names `ARCHEUS_HOME` deliberately (`:468`).
- Interactive sessions Archeus launches (`core/sessions/service.py:195`, `env=got.env`): cwd, settings sources and environment UNVERIFIED (T-053 already lists this as UNVERIFIED).

### Proposed card

```
### T-087 · Own calls stop inheriting Core's environment (T-053 P6, second clause)
owner: claude · status: proposed
auth: —
scope: Detached checkout from the T-072 candidate (b6ff773 or its successor). archeus/harnesses/calls.py (:92 Claude, :160 pi): the call's environment is config.account_env(home) with every PYTEST_* and ARCHEUS_* variable removed, by the same prefix filter as archeus/node/local.py:607-612 (one shared helper if both call sites use it; local.py itself unchanged unless the helper moves there); tests in tests/v1/unit/test_own_call_no_tools.py and tests/v1/integration/test_deputies.py. claude_sessions/config.py account_env unchanged (legacy TUI/GUI callers keep their behaviour). No execution, isolated-path or interactive-session change.
refs: T-053 P6 (:121-129) and O6 (:48-57); T-060, T-081, T-085, T-086; archeus/node/local.py:607-612.
accept: (1) a Claude and a pi own call, with ARCHEUS_HOME, ARCHEUS_DEBUG and PYTEST_CURRENT_TEST set in Core's environment, receive none of them; (2) they still receive the harness home variable (CLAUDE_CONFIG_DIR / PI_CODING_AGENT_DIR) with the account's value, PATH, and an unrelated user variable (stand-in for a provider key such as SPARK_QWEN_KEY); (3) ANTHROPIC_API_KEY is still dropped for Claude; (4) T-086's two variables are still set on a no_tools Claude call; (5) execution spawn environments unchanged.
verify: Fake callers capturing env (no real CLI); the existing deputies/own-call suites pass; ruff, no CR; mutants: filter dropped for Claude, for pi, ARCHEUS_ prefix only, PYTEST_ prefix only, filter applied before the home variable is set (would drop nothing relevant, so assert the home variable survives).
commits: —
review: —
notes: Drafted by Claude (fork, read-only on b6ff773). Exposure today is small after T-081/T-085/T-086 (no tools, safe mode, no extensions), and ARCHEUS_HOME reaches a call only when Core's own process has it set (user, tests, developer environment); this closes P6's second clause for the deputies by construction rather than by that. Interactive sessions (service.py:195) not mapped.
```

### Owner questions

1. **Filter shape.**
   - **A (recommended):** denylist by prefix (`PYTEST_`, `ARCHEUS_`), the same rule `run_check` already uses. Provider keys, proxies and certificates keep working.
   - **B:** allowlist (PATH, profile/temp variables, the harness home, named provider keys). Stricter, but every user's provider setup (pi's `$VAR` keys, corporate proxies, `NODE_EXTRA_CA_CERTS`) becomes a list to maintain, and a missing entry is a silent call failure.
2. **Interactive sessions.**
   - **A (recommended):** a separate read-only mapping card for `core/sessions/service.py` (cwd, settings sources, environment) before any change.
   - **B:** fold the same filter into session launch now. Not recommended: a session the user drives may legitimately want `ARCHEUS_*` (e.g. a user running `archeus` inside it), which is a product question.

## Part B. Native cards: the authorisation each needs

### Ground rules that apply to all three (from D:/Claude/CLAUDE.md and the board's hard rules)

- **No ACL is written anywhere.** S1 (`77008db`) removed every grant path and `test_the_boundary_has_no_acl_mutation_primitive` / the static gate in `test_pv20_isolation.py` fail on any ACL-writing API in `archeus/`, `claude_sessions/` or `tools/`. ACL code returns only with S2-G (T-004, BLOCKED BY OWNER on a design decision about peer exclusion). An authorisation here cannot override that; any step that needs a grant is **NOT ACCEPTABLE** under these cards.
- **Never the Python install, never a user repository, never anything shared.** The Python310 incident (a grant pointed at the real install) is the reason. A probe needing a runtime the AppContainer can read would need a grant on a staged copy, which is S2-G's; so the probes below use binaries every AppContainer can already execute (`C:\Windows\System32\…`, readable by ALL APPLICATION PACKAGES by Windows default) and parent-opened inherited handles for output, so no file needs an ACE.
- **No elevation, no system-wide state.** No `CheckNetIsolation LoopbackExempt` (admin, machine-wide, and it would answer a different question), no firewall rule, no service, no driver. If any step reports it needs elevation, the card stops and records it.
- **Production switches stay off**: `PRODUCTION_DISPATCH_ENABLED`, `A4_ENFORCED`, `isolation.CAPABILITIES = ()`, `CONFINED_VERIFICATION_ENABLED`. The probes call the node layer directly from a test.
- **Where**: pytest temp under a short Core-owned root (e.g. `--basetemp=D:/tNNN`, an `ARCHEUS_HOME` below it); a new detached checkout from the T-072 candidate; tests live in `tests/v1/integration/test_pv20_isolation_windows.py` (already the native file, ignored by the filtered run) and are skipped off Windows.
- **Cleanup**: every AppContainer profile created is deleted (`DeleteAppContainerProfile`), every Job closed (KILL_ON_JOB_CLOSE), the basetemp deleted; the card's report lists `archeus.*` profiles before and after (`HKCU\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppContainer\Mappings` and `%LOCALAPPDATA%\Packages\archeus.*`) and an `icacls <root> /save` digest of the basetemp root and of `Python310` before and after, which must be byte-identical.
- **Recovery if something is left behind**: a stale profile — `DeleteAppContainerProfile` by name (the node already has `is_stale_profile`, `isolation.py:104`); an orphan process — it is in a KILL_ON_JOB_CLOSE Job, so closing Core ends it, else `taskkill /T /PID`; an unexpected ACL change (should be impossible: no ACL API is called) — `icacls <path> /restore <saved>` from the before-snapshot, as in the Python310 recovery.

### Recommended order

1. **T-064 (loopback reach)** first: no ACL, no runtime staging, smallest surface, and it gates all broker code (T-065) and K-O4 item 1.
2. **T-068 (K-O4 origin)** second: read-only observations (connection owner, token, ACL reads) on top of T-064's probe.
3. **T-063 (A6-5 verifier)** last and **not authorisable yet as scoped**: its accept needs a verifier run with "the staged stdlib runtime", which an AppContainer can only read through an S2-G grant (T-004, BLOCKED BY OWNER). Either T-004 is decided first, or T-063 is re-scoped to the parts that need no grant (Job limit flags, deadline kill, output capture, profile teardown, "cannot read run/isolation, the DB or run/exec") with a System32 program standing in for the runtime; the staged-runtime half waits for S2-G.

### T-064 — authorisation text

> I authorise T-064 on this machine, under the current Windows user, without elevation: in a new detached checkout from the T-072 candidate, a test in tests/v1/integration/test_pv20_isolation_windows.py may (1) create one AppContainer profile per run with the node's own naming (`CreateAppContainerProfile`, zero capability SIDs) and delete it at the end (`DeleteAppContainerProfile`); (2) create a Job object with KILL_ON_JOB_CLOSE and start inside it, under that AppContainer token, only `C:\Windows\System32\curl.exe` and `C:\Windows\System32\cmd.exe` with parent-created inherited handles for stdout/stderr; (3) open, inside the same pytest process, one TCP listener on 127.0.0.1 on an ephemeral port and one named pipe with a per-run random name, and record whether the contained process can connect to each, and that a second, unannounced 127.0.0.1 port is also tried; (4) run with pytest basetemp under D:/ and delete it afterwards. Not authorised: any ACL change, any loopback exemption or firewall change, any capability SID, elevation, any path outside the basetemp other than reading System32, any production switch. Evidence: exit codes, connect results and errors per target, the profile list and icacls digests before/after, in the card's verify line.

### T-068 — authorisation text

> I authorise T-068 on this machine, under the current Windows user, without elevation, after T-064: the same AppContainer/Job/System32 probe as T-064, plus these read-only observations from the pytest process: `GetExtendedTcpTable` (owner PID of each loopback connection to the test listener), `OpenProcess` with query rights and `GetTokenInformation` on that PID (user SID, AppContainer SID, integrity level), `GetNamedSecurityInfo` on the listener's run/ directory and on the basetemp `ARCHEUS_HOME` tree as Core created it; observing a user process, an AppContainer process and a verifier principal (the A6 principal key with zero grants, `isolation.principal`); and a PID-reuse/early-exit case where the contained process exits before observation. Not authorised: any ACL write, loopback exemption, firewall change, capability SID, elevation, or reading any token or ACL of a process or tree the test did not create (other than System32 binaries). Evidence: per principal, the observation recorded verbatim; the early-exit outcome; the ACLs as read; profile list and icacls digests before/after.

### T-063 — authorisation text (as re-scoped; the full card waits for T-004)

> I authorise T-063 part 1 on this machine, under the current Windows user, without elevation: in a new detached checkout from the T-072 candidate, a test may run a verifier attempt through the node's real `run_confined_check` path in a fresh pytest `ARCHEUS_HOME` under D:/, with the AppContainer profile and Job the node creates (zero capability SIDs, KILL_ON_JOB_CLOSE, the `create_job` limit flags under test: process count and memory), a System32 program as the command, parent-inherited handles for output, and the profile deleted at the end; and may record whether the contained process can read `run/isolation`, `archeus.db` and `run/exec` of that `ARCHEUS_HOME`, that output is captured, that the deadline kills it, that the limits are observed, and that the profile is gone after teardown. Not authorised: any ACL grant (S2-G stays T-004's), staging or granting a Python runtime, the user's Python install, any shared tree, any production switch, elevation. Part 2 (the staged stdlib runtime) needs T-004 decided first.

Risk shared by all three if something goes wrong: a profile or a process left behind (recovery above); the realistic worst case is a stale `archeus.*` AppContainer profile entry in HKCU and an empty folder under `%LOCALAPPDATA%\Packages`, both removed by `DeleteAppContainerProfile`. No step writes an ACL, so the Python310-class failure is excluded by construction, and the before/after icacls digests prove it.
