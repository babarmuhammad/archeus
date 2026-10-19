# T-031 · The isolated execution's environment: a variable contract before implementation

Analysis only. Code is cited at `38497a2` (worktree `D:\archeus-pv20-s2-l`, read with `git show 38497a2:<path>`); docs at the same tree. Nothing was run: no tests, no CLI, no probe, no environment dump, no credential read. Variable names below are names, never values.

## 0. What this note does and does not do

It gives the contract every variable of an isolated execution's environment must satisfy, the merge order that exists today, and the smallest cards that would implement it. It does not change ordinary (unisolated) behaviour, which stays exactly as it is. It does not authorise a real-CLI run, a broker, a grant, or any production switch. And it does not treat Core's own environment as safe: Core inherits whatever the interactive user's shell had, so a value that comes from Core is still an untrusted input to the boundary unless Core derives it itself.

W-1's corrected environment (an explicit allowlist: SystemRoot, ComSpec, PATH, plus SystemDrive, windir, USERPROFILE, LOCALAPPDATA, APPDATA, TEMP, TMP; `W1-CLOSEOUT-2026-10-11.md` lines 38-40, in Codex's `pv20-evidence` folder outside the repo) made one fixture launch. The closeout says itself that it "does not identify which added variable resolved error 203, nor validate the production environment block". So W-1 is evidence that an allowlist can work. It does not show which variables production needs.

## 1. Where an isolated process's environment comes from today

Later rows win. Rows 1-5 are Core's; row 6 happens inside the process, where Core has no say.

| # | Source | What it adds or removes | Where | Isolated today | Ordinary today |
|---|---|---|---|---|---|
| 1 | Core's own process environment, copied whole | everything the user's shell or service gave Core | `base.py:316` (`env = dict(os.environ)`) | yes | yes |
| 2 | `spec.env` from the manager | `CAPABILITY_ENV` (`GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=''`, `SSH_AUTH_SOCK` removed, `GIT_CONFIG_COUNT=1` with `credential.helper=''`) and `ARCHEUS_HOOK_TOKEN` | `manager.py:65-67`, `:206`, `:225`; merged at `base.py:317-321` (a `None` value removes) | yes | yes |
| 2a | `spec.env`, Claude Code adapter layer | `CLAUDE_CONFIG_DIR` = `ExecPaths.config` (isolated) or the account home; `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` set to `None` by `setdefault` | `adapter.py:161-170`, applied at `:175` | config dir: private (T-024) | config dir: home |
| 2b | `spec.env`, fake adapter layer | `ARCHEUS_HOOK_CMD` (the hook argv as JSON) | `fake.py:104` | fake only | fake only |
| 3 | `base.spawn`, fixed | `ARCHEUS_EXECUTION_ID`, `ARCHEUS_HOME` (override anything above) | `base.py:322-323` | yes | yes |
| 4 | `base.spawn`, isolated branch | `TEMP` = `TMP` = `ExecPaths.tmp` | `base.py:333` | yes (T-024) | no |
| 5 | Isolated launch | the merged dict passed unchanged as the explicit, sorted Unicode block | `isolation.py:1160`, `:1176`, `:1965` | yes | — (`proc.spawn_detached`, `base.py:339`) |
| 6 | Inside the process | the CLI's own additions and any `env` block in a settings source it loads [DOC, not verified here]; the hook copies the env it is given (`hook.py:191`) and sets `ARCHEUS_HOOK_ACTIVE` for its own children (`hook.py:192`) | — | not Core's | not Core's |

Beside the environment, two paths that the process uses are fixed by Core outside it:
- **argv[0]** is resolved by Core (`adapter.py:95-96`, `shutil.which('claude')` against Core's `PATH`), so the child's `PATH` does not choose the CLI binary.
- **The hook command** is written into the Core-authored `--settings` file (`adapter.py:120-133`, `:138`) as `"<sys.executable>" "<repo>/archeus/harnesses/hook.py"` (`manager.py:41`, `:226`; quoted at `adapter.py:126`). It names Core's real interpreter and this repository. `default_plan` names the same two directories as its planned runtime and hook rows (`isolation.py:1134-1135`), which is why T-017 C4 stages copies. The hook then runs with the CLI's environment.

So for an isolated execution, every variable not in rows 2-4 is whatever Core's environment held. Today that is the user's full profile, `PATH`, proxy, interpreter and git variables, and every credential-shaped variable except the two `ANTHROPIC_*` names the adapter strips.

## 2. The contract, per variable class

Four actions: **OS** (a trusted operating-system value, derived by Core from an OS API where one exists, otherwise copied from Core's environment only after a check: absolute, and not inside the account home or the user's profile); **class 7** (an execution-private path under `ExecPaths.state`, `paths.py:150-152`); **removed**; **unknown** (a candidate exists, but whether the real CLI and its tools work with it needs a separately authorised run).

The recommended mechanism is an **allowlist**: the isolated block is built from nothing, from the rows below that say OS, class 7 or Core-set, and every other name is absent. A denylist cannot work here because the dangerous names cannot be enumerated (§2.5).

### 2.1 Directories

| Variables | Today, isolated | Candidate | Basis |
|---|---|---|---|
| `TEMP`, `TMP` | class 7 (`base.py:333`) | **class 7**, unchanged | PV-20 line 94; T-024 |
| `CLAUDE_CONFIG_DIR` | class 7 (`adapter.py:164-165`) | **class 7**, unchanged | ADR-0053 lines 268-271 |
| `USERPROFILE`, `HOME`, `HOMEDRIVE`, `HOMEPATH`, `APPDATA`, `LOCALAPPDATA` | the user's profile | **class 7**: a new `ExecPaths.home` under `own/state`, with `AppData\Roaming` and `AppData\Local` beneath it; `HOMEDRIVE`/`HOMEPATH` split from it. **Unknown** for what the CLI, Node and git do there | PV-20 line 94 ("home-equivalent directories"); ADR-0053 line 268 ("never receives the account home, a copy of it, or implicit access to account-home configuration"); T-017 §3 and Q5 |
| `SystemRoot`, `windir`, `SystemDrive`, `ComSpec`, `PATHEXT`, `ProgramFiles`, `ProgramFiles(x86)`, `ProgramW6432`, `CommonProgramFiles*`, `ProgramData`, `ALLUSERSPROFILE`, `PUBLIC`, `OS`, `NUMBER_OF_PROCESSORS`, `PROCESSOR_*` | inherited | **OS** | W-1 needed at least the first four |
| `USERNAME`, `USERDOMAIN`, `COMPUTERNAME`, `LOGONSERVER` | inherited | **removed** by default; **unknown** | names, not paths; nothing in Archeus reads them |

Profile variables pointing into class 7 rather than being removed is the recommended default. Without them, Windows tools fall back to the token's profile path, which under AppContainer is a different location Core does not control.

### 2.2 `PATH`, runtime and hook

| Item | Today, isolated | Candidate |
|---|---|---|
| `PATH` | Core's `PATH`, which commonly holds entries inside the user profile (per-user tool installs) | **Interim (with E1):** Core's `PATH` with every entry inside the account home or the user's profile dropped. **Final (with T-017 C4):** constructed by Core from the OS system directories plus the staged runtime and staged git. **Unknown**: the Windows CLI also needs a POSIX shell, located through `PATH` or a CLI-specific variable [DOC, not verified here] |
| Hook interpreter and script | Core's real Python and this repo (`manager.py:226`) | staged copies (T-017 C4); no environment variable involved |
| Hook interpreter startup | `python hook.py`: honours every `PYTHON*` variable and the user site directory | **`python -I hook.py`** for isolated executions (§3) |

### 2.3 Interpreter and shell startup influence

| Variables | Today, isolated | Candidate |
|---|---|---|
| `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`, `PYTHONUSERBASE`, `PYTHONNOUSERSITE`, `PYTHONSAFEPATH`, `PYTHONWARNINGS`, `PYTHONINSPECT`, `PYTHONIOENCODING`, `PYTHONUTF8` | inherited | **removed**. The hook is also run with `-I`, so it ignores them even if a later row admits one |
| `NODE_OPTIONS`, `NODE_PATH`, `NODE_EXTRA_CA_CERTS`, `NODE_TLS_REJECT_UNAUTHORIZED`, `npm_config_*` | inherited (the CLI is a Node program) | **removed**; **unknown** for `NODE_EXTRA_CA_CERTS` behind a TLS-inspecting proxy, which is P23's network question |
| `BASH_ENV`, `ENV`, `PERL5LIB`, `RUBYOPT`, `PSModulePath`, and the like | inherited | **removed**; **unknown** for `PSModulePath` (PowerShell rebuilds a default when it is absent [not verified here]) |

### 2.4 Git

| Variables | Today, isolated | Candidate |
|---|---|---|
| `CAPABILITY_ENV` (`manager.py:65-67`) | Core-set | **kept**, Core-set |
| `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, `GIT_CONFIG_KEY_<n>` beyond 0, `GIT_SSH`, `GIT_SSH_COMMAND`, `GIT_PROXY_COMMAND`, `GIT_EXEC_PATH`, `GIT_TEMPLATE_DIR`, `SSH_ASKPASS` | inherited | **removed**. An inherited `GIT_DIR` or `GIT_WORK_TREE` would point the execution's own git at another repository, which A1 forbids |
| `GIT_CONFIG_NOSYSTEM` | absent | **set to 1**; **unknown**: Git for Windows keeps its TLS and credential defaults in the system file, and `credential.helper` is already emptied by `CAPABILITY_ENV` |
| Global git configuration | the user's `~/.gitconfig`, through the inherited profile | follows `HOME` into class 7: the execution's own, empty unless it writes one |
| Commit identity (`GIT_AUTHOR_NAME`/`EMAIL`, `GIT_COMMITTER_NAME`/`EMAIL`) | from the user's `~/.gitconfig` | **Core-set** once decided: with the profile in class 7 an agent's commit has no identity and git refuses it. **Owner question 2** |

### 2.5 Credentials and Core's own variables

| Variables | Today, isolated | Candidate |
|---|---|---|
| `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` | stripped (`adapter.py:168-169`) | **removed** (unchanged) |
| Every other credential-shaped or provider-steering name: for example other `ANTHROPIC_*`, CLI OAuth-token variables, cloud-provider keys and profiles (`AWS_*`, Google/Vertex credentials), `OPENAI_API_KEY`, `GH_TOKEN`/`GITHUB_TOKEN`, `NPM_TOKEN`, and any `*_TOKEN`, `*_KEY`, `*_SECRET` | inherited | **removed**. These are examples, not a checked list; that the list cannot be completed is the reason for the allowlist |
| Provider access | none (R3-B not built) | only a Core-issued, execution-scoped broker credential, Core-set when R3-B exists (PV-20 lines 95, 243-251) |
| `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, `ALL_PROXY` | inherited | **removed**; **unknown**. Network is P23's |
| `ARCHEUS_EXECUTION_ID`, `ARCHEUS_HOME` | Core-set (`base.py:322-323`) | **kept**. The hook needs both (`hook.py:131`). `ARCHEUS_HOME` is a location, not a secret; keeping the local token there unreadable is the ACL's job (S2-G, T-004), not the environment's |
| `ARCHEUS_HOOK_TOKEN` | Core-set, minted per process (`manager.py:206`, `:225`) | **kept**. It authorises the mailbox and nothing else (PV-20 line 244); the agent's own tool commands inherit it, which the design accepts |
| `ARCHEUS_HOOK_WAIT` | inherited (`hook.py:38`): Core's environment sets the hook's deadline | **removed** (the hook uses its 60 s default), or Core-set if a different value is ever wanted |
| `ARCHEUS_HOOK_ACTIVE` | inherited: if present, the hook halts every call (`hook.py:133`) | **removed** |
| Other `ARCHEUS_*` (`DEBUG`, `NO_NOTIFY`, `BAT`, `RELAUNCH`, `UPDATE_TO`, `FREE`, `PLAN_TIMEOUT`, `HOOK_TIMEOUT`) | inherited | **removed** |
| `CLAUDECODE`, `CLAUDE_CODE_*` (present when Core itself runs inside a Claude Code session) | inherited | **removed**; **unknown** for a CLI-specific shell-path variable on Windows, decided with `PATH` |
| `LANG`, `LC_*`, `TZ`, `TERM`, colour variables | inherited | **removed** by default; **unknown**. The hook pins its own UTF-8 output (`hook.py:185-190`) |

Ordinary executions keep rows 1-4 of §1 exactly as today. Every candidate above applies only when `spec.isolation is not None`, which is the same switch T-024 used.

## 3. A finding: relocating the profile would open the hook's interpreter to the execution

The hook is Core's gate. It runs as `"<python>" "<hook.py>"` (`manager.py:226`, `adapter.py:126`), inside the process tree, with the CLI's environment. CPython at startup reads `PYTHON*` variables and imports from the user site directory, which on Windows lives under `%APPDATA%\Python`. Today that is the user's own profile. Once `APPDATA` points into class 7, which the execution can write, the execution could plant a `usercustomize.py` there or a `.pth` file. The next hook process would import it, and a hook running the execution's code can answer `allow` to anything.

The fix is one argument: run the hook with `python -I` (isolated mode, which implies `-E` and `-s`: no `PYTHON*` variables, no user site, no script directory on `sys.path`). The hook is standard library only with no package imports (`hook.py` docstring, lines 6-8), so it needs nothing those mechanisms provide. This is why `-I` must land **before or with** the profile relocation, never after. The staged runtime (T-017 C4) closes the remaining route, the interpreter's own installation directory, which must not be writable from inside.

## 4. The execution's environment versus Core's own git and verifier environments

They are three separate blocks and none is derived from another.

| Block | Built today | Contract |
|---|---|---|
| Execution | §1 | §2 |
| Core's git runner (`proc.run`/`proc.git` with `env=None`, so Core's whole environment: `proc.py:47`, `:64`), used by `git_branch` (`local.py:288`), `end_state` (`local.py:336`), `git_snapshot` (`local.py:421`) and the other helpers | Core's environment, including the user's global and system git configuration | Not this card. A5 (PV-20 lines 176-185) requires the Core-pinned configuration for every Core git operation over execution-derived content; that is T-016 W6 and T-030's ground. It must never be built from the execution's block, and the execution's block never needs Core's pinned git variables |
| Verifier (`run_check`: Core's environment minus `PYTEST_*`, plus two values, `local.py:499-500`) | Core's environment | A6's (ADR-0053 lines 250-266): its own home, scratch and temp, and no credential, token or Core state. Not this card |

## 5. Resume, continuation and retry

- **The same execution's later process** (a PAUSED or AWAITING_APPROVAL resume goes through `_spawn` again, `manager.py:611`): the block is rebuilt from nothing by `base.spawn`, because nothing of an environment is stored. The class-7 paths are the same (`ExecPaths` is derived from the execution id). `config` must exist, or the spawn is refused (T-024). `tmp` and the proposed `home` are created if missing and never reset. The hook token is new, because `_spawn` mints one per process (`manager.py:206`) and `prepare_process` records its digest.
- **A hand-off continuation, or a retry:** a new execution, so new `ExecPaths`, fresh empty class-7 directories and a new token. Nothing of the predecessor's environment or `home` carries over; its context arrives as the checkpoint in the prompt.
- **Teardown:** ADR-0053 says the config directory is torn down with the execution. Today nothing deletes `run/exec/<id>/`, and retention stays keep-all unless separately authorised (board guidance).

## 6. Proposed cards

**E1 · The isolated environment block, built by allowlist.**
- Files: `archeus/harnesses/base.py` (isolated branch of `spawn`, and the allowlist beside it); `archeus/infra/paths.py` (`ExecPaths.home`); `tests/v1/unit/test_pv20_private_config.py`, or a new focused `tests/v1/unit/test_pv20_isolated_env.py`. The existing seam is `FakeIsolation.launch`, which records the env it is given (`test_pv20_private_config.py:22-35`).
- For `spec.isolation is not None`: start from the OS rows of §2.1, filtered as §2 says; apply `spec.env` (Core-authored: the manager and the adapter); then the Core-set rows (`ARCHEUS_*`, `TEMP`/`TMP`, the profile variables into class 7, `GIT_CONFIG_NOSYSTEM`); then the interim `PATH` filter. The ordinary branch is untouched.
- Tests, with synthetic values only:
  - with synthetic credential-shaped, `GIT_DIR`, `GIT_CONFIG_PARAMETERS`, `NODE_OPTIONS`, `PYTHONPATH`, proxy, `ARCHEUS_HOOK_ACTIVE` and `ARCHEUS_HOOK_WAIT` values in `os.environ`, none reaches the launch, and the key set is within the allowlist plus the Core-set names;
  - no value names the account home or the (synthetic) user profile, and no `PATH` entry lies inside either. This reinstates T-017's withdrawn `test_an_isolated_env_names_nothing_inside_the_account_home`, which only becomes true once the whole block is covered;
  - the profile variables point into `ExecPaths.home`;
  - a Core-set value wins over an inherited one of the same name;
  - the ordinary launch env is exactly today's;
  - a resume rebuilds the block with the same private paths;
  - a continuation (another execution id) gets different private paths.
- Mutants: copy `os.environ` wholesale on the isolated branch; let an inherited name override a Core-set one; drop the profile relocation; drop the `PATH` filter.
- Dependencies: none open (T-024 and T-029 are in `base.py` and done). E2 must land first, or in the same change (§3).

**E2 · The hook runs in isolated mode.**
- Files: `archeus/core/execution/manager.py` (`hook_settings`, line 226), for isolated executions; `tests/v1/unit/test_execution_units.py` (the existing `_spawn` rig records the spec).
- Tests: the isolated spec's hook command carries `-I` and the ordinary one is unchanged. One real-interpreter test (a Python subprocess, as the existing hook tests already run; not the CLI) plants a synthetic `PYTHONPATH` module and a user-site `usercustomize` in temp directories and shows the `-I` hook ignores both.
- Overlap: T-017 C4 rewrites the same line to point at staged copies, so E2 either lands first or is folded into C4.

**E3 · `PATH` constructed by Core** (with T-017 C4): system directories from the OS plus the staged runtime and staged git, replacing E1's interim filter. It cannot be written before C4 decides what is staged.

**Separately gated (not a code card):** a real-CLI run under an `auth:` naming it (T-008's kind) to learn which further OS variables the production CLI, Node and git need. The allowlist grows only from that evidence, one named variable at a time.

## 7. Engineering defaults recommended here, not owner questions

- an allowlist, not a denylist (§2.5);
- the profile variables into class 7, not removed (§2.1), which answers T-017 Q5 unless the owner says otherwise;
- the hook interpreter with `-I` (§3);
- `ARCHEUS_HOOK_WAIT`, `ARCHEUS_HOOK_ACTIVE` and the other `ARCHEUS_*` removed;
- `GIT_CONFIG_NOSYSTEM=1`, proxies removed, locale removed, each marked unknown until the gated run;
- on a resume, `home` behaves like `tmp` (created if missing, never reset), and only `config` is refused when missing.

Each is reversible in one place (`base.py`'s allowlist, or one argument in `manager.py`).

## 8. What stays unverified

What the production CLI, Node, git and a POSIX shell need in the block; whether the CLI writes outside `CLAUDE_CONFIG_DIR` when the profile variables point into class 7; whether an explicit block without a variable makes Windows itself fall back to something outside class 7; and whether an `env` block in a settings source the CLI loads is applied to the hook and to tool commands. A fake test proves only that Core built the block it meant to build.

## 9. Noticed outside this card

Under isolation, an opted-in `project` or `local` settings source still loads directly from the workspace (T-028 kept those sources following their opt-ins). ADR-0053 lines 275-276 say opt-ins enter only as Core-materialised data, and a workspace settings file is execution-influenced. It can carry an `env` block, more hooks, or settings that weaken hooks [not verified against the CLI]. It is unreachable today: T-027 refuses isolated projects, and an account can opt in only `user` (`entities.py:1436`), so a project-less execution has no project or local opt-in. It becomes reachable when T-030 seeds isolated projects, and belongs on that path or a T-028 follow-up.

## 10. Owner questions

1. **Allowlist and its cost.** Accept that the isolated environment is built from an allowlist and fails closed: until the gated real-CLI run shows what the CLI needs, an isolated launch may fail on a missing variable rather than start with an inherited one. Or keep inheriting Core's environment and strip a list?
2. **Commit identity inside the execution's own repository.** With the profile in class 7, the agent's commits need an identity Core sets. Core's identity (`Archeus <archeus@localhost>`, which Core's snapshot already uses, `local.py:31`), or the user's name and email copied as plain data (no credential)?
3. **T-017 Q5.** This note recommends pointing `USERPROFILE`, `HOME`, `HOMEDRIVE`/`HOMEPATH`, `APPDATA` and `LOCALAPPDATA` into an execution-private `home` under class 7, rather than removing them. Confirm, or choose removal.
