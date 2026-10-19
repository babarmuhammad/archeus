# T-017 · A2 private configuration and environment: exact slice contract

Prepared by Claude, 2026-10-12. Planning only: no code, no test run, no OS call, no credential read, no design ruling.

Sources:
- Canonical: `docs/architecture/pv20-execution-isolation-design.md` §3.1 (rows at lines 93-95, exclusions at 101-112), §3.3 (R3-B at 243-253), §3.5, §3.7 (migration at 406-411), §6 items 15 and 22, §7.1 (lines 681-695), §7.5 (class 7 at 832-852); `decisions/ADR-0053.md` A2 (lines 267-283) and its consequence list (line 408-411); `decisions/ADR-0049.md` "PV-20 consequence" (lines 158-182).
- Code: S2 worktree `D:\archeus-pv20-s2-l`, branch `pv20-s2`, HEAD `3489a39`. Everything cited below was read at that commit and nowhere else.
- Not opened: any credential, account-state or `.claude.json` file. Credential locations are named only as the source code names them.

## 1. Inventory: what an execution's CLI is given today, against A2

> **Qualified by Correction C-1012-T017 §3:** "fresh, per-execution" means per execution, not per process. A PAUSED resume keeps the same private configuration.

What A2 requires (ADR-0053 lines 267-283, design §6 item 22):
- `CLAUDE_CONFIG_DIR` is a fresh, Core-created, per-execution directory in class 7, holding no provider login, torn down with the execution.
- The execution never receives the account home, a copy of it, or implicit access to its configuration.
- Core-authored spawn configuration is Core-write / execution-read, outside that directory.
- Opt-ins enter only as Core-materialised data carrying no credential authority. No MCP opt-in is admitted to an isolated execution.

| Surface | Today, at `3509a39`'s parent `3489a39` (file:line) | What A2 requires | Gap |
|---|---|---|---|
| `CLAUDE_CONFIG_DIR` | The account home: `ClaudeCodeAdapter._env` sets it to `os.path.expanduser(spec.account.home_ref)` (`archeus/harnesses/claude_code/adapter.py:157-161`). The home comes from the account row or the routing decision's snapshot (`archeus/core/execution/manager.py:198-200`). No branch on isolation. | A fresh Core-created class 7 directory | Whole row |
| Provider credential in the env | `_env` sets `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` to `None` (`adapter.py:162-163`), and `base.spawn` drops `None` values from the inherited env (`archeus/harnesses/base.py:322-327`). | No provider credential inside the boundary (design §3.5, §6 item 15) | None found for those two names. Whether the CLI reads other credential variables is not verified here. |
| Login store | The CLI finds its login under `CLAUDE_CONFIG_DIR`. In source the only name for it is `.credentials.json` under the account's config dir (`claude_sessions/usage.py:50`), read Core-side by `authenticate` (`adapter.py:111-114`, `archeus/harnesses/calls.py:73`). | Never inside the boundary; provider access via R3-B | Follows from the `CLAUDE_CONFIG_DIR` row: pointed at the home, the CLI would look for the login there. |
| `own/state` (class 7) | **A path in the plan, not a relocation of the CLI's state.** `ExecPaths.state` = `run/exec/<id>/own/state` (`archeus/infra/paths.py:150`). It appears only as the `state` grant row and `state_dir` of `default_plan` (`archeus/node/isolation.py:1139`, `1144`) and in the invariant's separation check (`isolation.py:248`). Nothing creates the directory (`base.spawn` creates `dir`, `req`, `res`, `ctl` only, `base.py:301`) and no env variable names it. | The CLI's configuration and runtime state live there | Whole row. This is the qualification Codex asked T-012 to record (`reviews/T-012-3489a39.md` finding 2). |
| Temp and home-equivalent dirs | `base.spawn` starts from `dict(os.environ)` (`base.py:322`), so `TEMP`, `TMP`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `HOMEDRIVE`/`HOMEPATH` are Core's. On the isolated path that merged env is passed as the explicit block (`isolation.py:1961`). | "temporary and home-equivalent directories the processes need" are class 7 (design line 94) | Whole row. What the CLI, Node and git do with an unwritable `TEMP` under AppContainer is not verified. |
| Core-authored spawn configuration | `res/settings.json` written by Core (`adapter.py:116-127`); `res/mcp.json` written by `sources.flag_argv` when MCP servers are opted in (`archeus/harnesses/sources.py:344-353`, called with `exec_dir=res` at `adapter.py:138`). | Class 2, Core-write / execution-read; `mcp.json` **not written** for isolated executions (ADR-0053 line 409) | `mcp.json` is written whenever an MCP opt-in exists, isolated or not. Nothing in `archeus/node` refuses or strips an MCP opt-in (grep `mcp` in `isolation.py`, `local.py`: no hit). |
| Plugin opt-ins | `--plugin-dir` names the plugin's install path **inside the account home** (`sources.plugin_dir`, `sources.py:153-167`; emitted at `sources.py:355-358`). | Materialised by Core into class 2, or excluded with a reason (ADR-0049 lines 168-172) | Whole row: the execution would be pointed into the home. |
| `user` setting source, account `CLAUDE.md` | When `user` is opted in, `--setting-sources user` (`sources.py:347`) makes the CLI read `settings.json` under `CLAUDE_CONFIG_DIR`. The inventory predicts this from the account home (`sources.take`, `sources.py:207`, `306`). | Only as Core-materialised data (ADR-0049 item 1-2) | With a fresh `CLAUDE_CONFIG_DIR` the inventory, still read from the home, would predict items the CLI no longer loads. |
| Hook interpreter and script | `hook_settings=(sys.executable, HOOK)` (`manager.py:213`), `HOOK` = this repo's `archeus/harnesses/hook.py` (`manager.py:41-42`), written into the settings command (`adapter.py:121-125`). The hook imports only `json`, `os`, `re`, `sys`, `time` (`hook.py:32-36`). | Read/execute on Core-provided material that holds no user secrets (design §3.1 row 3, R7) | The plan's `runtime` and `hook` rows name the real Python install and the repo (`isolation.py:1134-1135`); the code comment there says access waits for "Core-staged copies". No staging code exists (grep: none). |
| The CLI itself, shells, git | `ClaudeCodeAdapter._find` = `shutil.which('claude')` (`adapter.py:91-92`). | Read/execute (design §3.1 rows 1-2) | No row in `default_plan` names the CLI, Node, a shell or git; `REQUIRED_GRANTS` has no such row (`isolation.py:124`). Whether one is needed depends on where they are installed and on the existing ACL there; not verified. |
| Broker | `default_plan` sets `broker=''` (`isolation.py:1145`); condition 2 fails without one (`isolation.py:210`, `218`). | R3-B | No broker exists. This is why no production isolated execution can start today. |
| Resume state | `--resume <session>` (`adapter.py:139`, `175-180`) is resolved by the CLI from its own store under `CLAUDE_CONFIG_DIR`. | Where transcripts and resume state live is listed as unverified (design line 694) | Under A2 the store moves into class 7 with the config dir. Nothing removes `run/exec/<id>/` today (no `rmtree` in `archeus/node`, `archeus/harnesses`, `archeus/core/execution`). |

Core-side reads of the account home stay legitimate under A2, because Core runs as the user: `sources.take` (inventory), `authenticate`, and the usage feed (`archeus/core/routing/usage.py:59-64`). A2 restricts what the execution receives, not what Core reads.

## 2. Slices

Each slice is fake-only: no real CLI, no AppContainer, no ACL write, no network. None of them lets a production isolated execution start: condition 2 still fails on the missing broker and on the unstaged or ungranted runtime and hook rows. Test file choices avoid `test_execution_units.py` and `test_execution.py` where possible, because T-015 claims them.

### C1 · Private config and temp directory for an isolated spawn

> **Qualified by Correction C-1012-T017 §1 and §3:** its evidence covers only the variables it changes, and its directories are kept across a resume. Two of its tests are replaced there.
- **Files:**
  - `archeus/infra/paths.py`: two `ExecPaths` attributes under `own/state`, e.g. `config` and `tmp`. The names are a layout choice (R2 is an implementation constraint).
  - `archeus/harnesses/base.py` (`spawn`): for `spec.isolation is not None`, create both directories beside the class directories (`base.py:301`), and set `TEMP`/`TMP` to `tmp` in the merged env.
  - `archeus/harnesses/claude_code/adapter.py` (`_env`, module docstring lines 17-19): for `spec.isolation is not None`, set `CLAUDE_CONFIG_DIR` to `config`, never the home. Unisolated behaviour stays as it is.
  - `tests/v1/unit/test_pv20_isolation.py` (new class).
- **Depends on:** nothing. `LocalNode.spawn` already attaches `spec.isolation` before `adapter.start` (`archeus/node/local.py:60-65`), so `_env` can see it. The adapter only reads the node's decision and makes none.
- **Fake acceptance tests:**
  - `test_an_isolated_spec_gets_a_private_config_dir`: `_env` returns `CLAUDE_CONFIG_DIR == ExecPaths(eid).config`.
  - `test_an_isolated_env_names_nothing_inside_the_account_home`: no value in the env block given to the fake launch is the home or lies inside it (normcase, realpath).
  - `test_an_unisolated_spec_keeps_the_account_home`: pins today's behaviour.
  - `test_core_creates_the_private_dirs_before_the_process`: the fake `launch` asserts both directories exist when it is called.
  - `test_an_isolated_env_points_temp_at_private_state`: `TEMP` and `TMP` equal `ExecPaths(eid).tmp`.
  - `test_no_provider_credential_variable_reaches_an_isolated_env`: with both `ANTHROPIC_*` names set in `os.environ`, neither reaches the launch env.
  - `test_no_spawn_path_reads_the_account_login`: a static gate. Neither `.credentials.json` nor `usage._creds` is referenced in `archeus/node` or `archeus/harnesses/base.py`. Today's only references are `authenticate` (`adapter.py:113`, `calls.py:73`) and `claude_sessions/usage.py`.
  - Mutation: removing the isolation branch in `_env` fails the first two tests; removing the `makedirs` fails the fourth.

### C2 · Isolation decided before the inventory; isolated inventory excludes MCP and unmaterialised opt-ins

> **Decision half superseded by Correction C-1012-T017 §2** (T-021 slice D1). The exclusion half stands.
- **Ordering problem found while reading:**
  - The manager takes and stores the inventory (`manager.py:224-235`), then `node.spawn` decides isolation (`local.py:59-62`).
  - The inventory therefore cannot record an isolated execution's exclusions, and the argv is derived from the stored inventory (`sources.py` module docstring lines 12-14).
  - So the decision has to be known first.
- **Files:**
  - `archeus/core/execution/manager.py`: ask the node before `adapter.inventory`, then pass `isolated=` to `node.spawn`, which already accepts it (`local.py:49`).
  - `archeus/node/local.py`: a decision accessor, reusing `Isolation.requested`.
  - `archeus/harnesses/sources.py` (`take(..., isolated=False)`). When true:
    - every MCP server is `excluded` with an A2 reason and `flags['mcp_servers'] = []`, so `flag_argv` writes no `mcp.json`;
    - plugin opt-ins, the `user` source and the account `CLAUDE.md` are `excluded` with reason "not materialised" until C3 exists.
  - `archeus/harnesses/claude_code/adapter.py` (`inventory`).
  - Tests: `tests/v1/unit/test_settings_sources_units.py`, plus one ordering test in `test_execution_units.py` (T-015's file, see §5).
- **Depends on:** T-015 landing first, or an explicit split of `manager.py`.
- **Fake acceptance tests:**
  - `test_an_isolated_inventory_admits_no_mcp_server`: an opted-in server comes out `excluded` with a reason, there is no `--mcp-config`, and no `res/mcp.json` file.
  - `test_an_isolated_inventory_never_predicts_an_account_home_item_loaded`: no item sourced from the home has status `opted_in`.
  - `test_an_isolated_argv_names_no_path_inside_the_account_home`: no `--plugin-dir` into the home.
  - `test_an_unisolated_inventory_is_unchanged`: the existing `test_settings_sources_units.py` cases pass unchanged.
  - `test_isolation_is_decided_before_the_inventory_is_taken`: a fake node records the order of calls.

### C3 · Materialise opt-ins into class 2 (later; needs evidence first)
- **Fixed by ADR-0049 (lines 168-172):** Core writes the materialised item where the execution can read but not write it, beside the hook settings. An item that would bring an MCP server, an environment block or a credential helper is excluded and recorded.
- **Open (questions 3 and 4):**
  - how the CLI is made to load a materialised `user`-source item or the account `CLAUDE.md` from class 2 while its `user` source resolves to the class 7 config dir;
  - how Core detects those three properties in a plugin directory.
- **Not sliced here.** It depends on CLI evidence (§4) and owner answers.

### C4 · Staged runtime and hook copies (no ACL)
- **Files:**
  - `archeus/infra/paths.py`: a staging directory under `ARCHEUS_HOME` and its entry in `V1_OWNED` (`paths.py:28`).
  - The stager itself: beside `default_plan` in `archeus/node/isolation.py`, or its own module if review prefers.
  - `default_plan`: its `runtime` and `hook` rows name the staged paths.
  - `manager.py:213`: an isolated execution's `hook_settings` name the staged interpreter and script (T-015's file again).
- **Ownership:**
  - Core creates and owns the staged tree.
  - The execution gets read/execute only.
  - It holds no user secrets (R7, design §3.1 line 78).
  - Staging is **copy, never hardlink**: a hardlink shares its ACL with the original. That is the 2026-10-08 incident recorded in `CLAUDE.md`'s Python310 gotcha.
- **Depends on:**
  - Nothing, for staging alone.
  - Applying access to the staged copies is S2-G's work, so T-004 (BLOCKED BY OWNER).
  - What Python needs at startup beyond the five modules the hook imports is not enumerated here.
- **Fake acceptance tests:**
  - `test_the_staged_runtime_is_a_copy_not_a_link`: every staged file has `st_nlink == 1` and a different file index from its source.
  - `test_staging_writes_only_under_archeus_home`.
  - `test_default_plan_names_no_path_in_the_python_install_or_the_repo`: the `runtime` and `hook` rows lie outside `dirname(sys.executable)` and outside the repo.
  - `test_an_isolated_hook_command_names_the_staged_pair`.
- The CLI binary, Node, shells and git are **not** covered by C4 (see §1, last rows).

### Not a slice: credentials (broker prerequisites)
No code slice exists until these hold. Each is listed, none is decided here.
1. Evidence that the production Claude CLI reaches its provider through a Core broker (design §7.1 line 681, unverified; R3-B approved as the target, §6 item 15).
2. Network reach from the isolated identity:
   - `CAPABILITIES = ()` holds no network capability (`isolation.py:63-66`), and network is P23's.
   - Any loopback reach the broker needs is subject to R1 (design line 96).
   - Whether and how an AppContainer process reaches a loopback listener is not verified here.
3. An execution-scoped credential with zero Core scopes, never accepted by Core's API (design §3.3 lines 243-249).
4. How the CLI is told to use the broker. The CLI's configuration surface for this is not verified here.
5. If 1 fails: R3-A is a separate owner security decision (§6 item 15). Until then isolated Claude Code executions do not run.

Never, in any slice:
- a grant on the account home;
- copying the login file, or any part of it, into class 7;
- passing a provider credential variable into the env.

## 3. Separate later item: production environment validation
This is not a slice of T-017. It needs Windows runs under an `auth:` naming the operation, like T-008, and stays separate from every slice above. The items, from design §7.1 lines 692-695 and this inventory:
- the CLI starts with a fresh `CLAUDE_CONFIG_DIR` holding no login;
- Core-authored configuration stays read-only and settings precedence holds;
- where transcripts and resume state land;
- what the CLI, Node and git do with `TEMP`/`TMP` in class 7 and with the inherited profile variables;
- whether the CLI install path needs a row;
- the A2 acceptance line (design line 915): the account home reads access-denied, and Core-authored configuration is not writable from inside.

## 4. Owner and design questions (not answered here)
1. **Teardown.** A2 says the config dir is "torn down with the execution" (ADR-0053 line 271), and the CLI's transcripts live in it. Are they kept or exported before teardown, and where? Today nothing deletes `run/exec/<id>/`.
2. **Staged runtime granularity.** One shared staged copy with a read/execute ACE per execution SID (R7 permits shared read/execute material), or a copy per execution?
3. **Materialised `user` source and account `CLAUDE.md`.** Options:
   - merge them into the class 2 `--settings` file, which may change precedence;
   - put a copy in the class 7 config dir, which is execution-writable and so not Core-authoritative;
   - another route.

   This needs CLI evidence first.
4. **Interim policy.** Until C3 exists, are every plugin, `user`-source and account-`CLAUDE.md` opt-in excluded for isolated executions (fail closed, C2 as written), or does isolated dispatch wait for C3?
5. **Profile variables.** `USERPROFILE`, `HOME`, `APPDATA` and `LOCALAPPDATA` in the isolated env could be pointed into class 7, dropped, or left as they are. Git's global configuration lookup interacts with A5's Core-pinned configuration, which is T-016's ground.
6. **Where the isolation decision is asked.** C2 moves the question ahead of the inventory. A remote node would need the same accessor; today the manager reaches node isolation only through `getattr` probes (`manager.py:706`, `759`, `775`).

## 5. File overlap
- **T-015:**
  - `manager.py`: C2 (decision before inventory) and C4 (`hook_settings`, line 213).
  - `test_execution_units.py`: C2's ordering test.

  C1 touches neither. C2 and C4 wait for T-015 or need an explicit split.
- **T-016:** possible overlap on `archeus/infra/paths.py` (`ExecPaths`) and `archeus/harnesses/base.py` (`spawn` directory creation), if T-016's private-workspace slices change `own/work` creation there. Not checked against T-016's note, which did not exist when this was written.

## Noticed outside this card

> **Bounded by Correction C-1012-T017 §4:** existing W-1 evidence on the global STOP is stated there, and what stays unverified is narrowed.

The hook reads the global STOP at `<ARCHEUS_HOME>/run/STOP` (`hook.py:149`). `default_plan` names `run/` as Core state that must stay ungranted (`core_state=run_dir()`, `isolation.py:1144`). How an isolated hook reads the global STOP is therefore a class 3 layout question for the S2 layout, not for this card. Its effect under the isolated identity is not verified.

## Correction C-1012-T017 (2026-10-12, after reviews/T-017-analysis.md)

Appended; nothing above is reworded. Where this section and the text above disagree, this section holds. Each finding of the review is answered in the section with its number.

### 1. C1's evidence is about named variables, not the whole environment (finding 1)

C1 changes three variables for an isolated spawn: `CLAUDE_CONFIG_DIR`, `TEMP` and `TMP`. The rest of the environment still comes from `dict(os.environ)` (`base.py:322`). That includes `USERPROFILE`, `HOME`, `HOMEDRIVE`/`HOMEPATH`, `APPDATA`, `LOCALAPPDATA` and `PATH`, and the settings file still names the runtime and hook paths (`manager.py:213`, `adapter.py:121-125`). Any of these can name the account home, an ancestor of it, or a path inside it. A `PATH` entry under the home is one example.

So the C1 test `test_an_isolated_env_names_nothing_inside_the_account_home` claimed more than C1 delivers, and is replaced by:
- `test_an_isolated_claude_config_dir_is_never_the_account_home_or_inside_it` (normcase, realpath);
- `test_an_isolated_env_points_temp_and_tmp_at_private_state` (already listed; unchanged).

What the rest of an isolated environment may carry is an **open contract**, not part of C1. For each inherited variable it must say one of: points into class 7, dropped, or left. And for `PATH` and the hook/runtime paths, what they may name. That is §4 question 5 of this note, and it interacts with A5's pinned git configuration (T-016 W6). No test asserts anything about the whole environment until that contract exists.

### 2. One isolation decision (finding 2)

C2's first half (ask the node before the inventory, add a decision accessor in `local.py`) is replaced by `T-021-isolation-decision-contract.md` slice D1. `_spawn` takes `Isolation.requested` once, before `_workspace` and the inventory, and passes that value to `node.spawn`, which no longer decides. If the decision raises, nothing starts. C2's second half stays as written: `sources.take(..., isolated=...)` excludes MCP servers and unmaterialised opt-ins. It now receives D1's value and adds no accessor of its own. C4's `hook_settings` choice (`manager.py:213`) reads the same value. File edges: C2 and C4 land after D1. C2's ordering test `test_isolation_is_decided_before_the_inventory_is_taken` is superseded by T-021 §5's first test.

### 3. First launch versus a PAUSED resume (finding 3)

"Fresh, Core-created, per-execution" (§1, from ADR-0053 lines 267-283) is per **execution**, and one execution can have several processes: a PAUSED or AWAITING_APPROVAL resume starts a new process of the same execution with `--resume <session>` (`adapter.py:139`, `175-180`). The CLI resolves that session from its own store, which under A2 sits in the private `CLAUDE_CONFIG_DIR`. So, for C1:
- **First process** (`process_seq` 1): Core creates `config` and `tmp` empty.
- **Resume** (same execution, later `process_seq`): Core reuses the same directories with their content. It does not delete, reset or re-create them. `base.spawn`'s per-process cleanup (`base.py:305`: `ended`, `halted.json`) must not grow to touch `own/`.
- **Missing private configuration at resume**: never fall back to the account home. The spawn fails closed. Which refusal kind applies (`binding`, or a charged one) is a new owner question, Q7 below.
- **Hand-off continuation**: a new execution (`handoff_from`), so it gets its own fresh directories. Its context comes from the checkpoint in its prompt (`manager.py:202-205`), not from the previous execution's session store.
- **Teardown** happens only when the execution has ended (`_release_isolation` on an end state), never between its processes. What is kept or exported before that is §4 Q1, unchanged.

Tests replacing `test_core_creates_the_private_dirs_before_the_process`:
- `test_a_first_isolated_process_gets_new_empty_private_dirs`;
- `test_a_resume_reuses_the_private_dirs_and_keeps_their_content`: a file planted in `config` before the resume is still there, and `CLAUDE_CONFIG_DIR` is unchanged;
- `test_a_resume_without_its_private_config_never_uses_the_account_home`: the directory is removed before the resume; no launch, and no env value is the home;
- `test_a_hand_off_continuation_gets_its_own_private_dirs`.

### 4. The global STOP: existing evidence and what stays open (finding 4)

An ungranted `run/` on its own does not show that the global STOP is unreadable to an isolated hook. Nor does it show that the hook would halt at every tool call. Existing bounded evidence, from Codex's `W1-CLOSEOUT-2026-10-11.md` (one fixture, one account, build 26300; line 55 limits it to that fixture):
- row `global-stop` (line 24): a **present** Core-only STOP: "read denied; hook halted without request". The read was denied and the hook failed closed, as S0's determination intends for anything not "absent".
- row `clear` (line 23): "Request created; class-2 synthetic response accepted; allow". The hook reads the global STOP before the request (design §7.4 Gap A), so in that fixture an **absent** global STOP did not halt the hook. That reading is my inference from the table; the closeout does not state the determination for this case separately.

Still unverified, and not settled by reading:
- whether W-1's fixture placed the global STOP the way the product plan does: `<ARCHEUS_HOME>/run/STOP` (`hook.py:149`) under a `run/` that `default_plan` keeps ungranted (`isolation.py:1144`);
- so whether, under the product plan, an absent STOP reads as absent and a present one as denied.

That is product-plan sentinel verification. It belongs to an authorized Windows evidence card (T-008's kind), not to this note. No ancestor grant on `run/` or `<ARCHEUS_HOME>` is proposed. Mirroring the global STOP into each execution's class 3 `ctl/` is one alternative; it is a layout choice for the S2 owner, not decided here.

### Questions added
7. **Resume without its private configuration.** If an isolated execution's `config` directory is missing at resume, which refusal applies: uncharged `binding`, or charged? Falling back to the account home is excluded either way.
