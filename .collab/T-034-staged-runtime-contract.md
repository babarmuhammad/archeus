# T-034 · C4: staged runtime and hook — implementation contract

Prepared by Claude (a read-only fork), 2026-10-13. Analysis only: no runtime inventory or copy, no installed-CLI or provider call, no dependency install, no environment values, no tests, no native experiment, no credential read. Code is cited at `7675095` (the S2 worktree's HEAD when this was written; read with `git -C D:/archeus-pv20-s2-l show 7675095:<path>`). T-033 is being implemented concurrently in `base.py`, `paths.py` and `manager.py`; nothing here depends on its unfinished code.

Markers used below:
- **[CODE]** read in the source at `7675095`.
- **[SPIKE]** observed by the 2026-10-08 spike (`HANDOFF-PV20-SPIKE.md`, `.spike/spike_host.py`, both untracked under `D:\Claude`). Spike evidence is one synthetic fixture on build 26200.
- **[DOC]** documented Windows, CPython or Node behaviour, stated from the public documentation and not re-read or tested for this note.
- **[UNVERIFIED]** nobody has observed it for this product. Each one belongs to the separately gated real-runtime run (§8).

## 0. What this note does and does not do

It maps how the interpreter, the CLI and the hook are resolved today, and specifies the smallest staged-runtime slice for the **hook**: a Core-owned copy of the interpreter closure and of `hook.py`, placed outside every execution-writable directory, with an integrity manifest, wired into an isolated execution's `hook_settings` and into `default_plan`'s `runtime` and `hook` rows.

It does not:
- grant anything. Applying read/execute access to the staged copy is S2-G's work (T-004, BLOCKED BY OWNER). The static ACL gate in `test_pv20_isolation.py` (`ACL_APIS`, line 1148; `test_no_acl_mutation_primitive_exists_in_production_code`, line 1462) stays as it is.
- stage the CLI, Node, a shell or git. T-017 C4 already excluded them (`T-017-private-config-plan.md:110`). §5 says what is unknown about them and what the gated run must answer.
- copy credentials, build a broker or activate anything. Production dispatch stays off.
- claim that copying plus `-I` makes the runtime immutable to the execution or proves CLI compatibility (§6, §7).

## 1. Who resolves which executable, where and when (today)

| # | What is resolved | Resolved by | How, and against what | When | Isolated today |
|---|---|---|---|---|---|
| 1 | The CLI binary (argv[0]) | Core | `ClaudeCodeAdapter._find` = `self._exe or shutil.which('claude')` against **Core's** `PATH` (`adapter.py:95-96`) [CODE] | Every `argv()` call, i.e. every process (`adapter.py:135-136`) | Same. The absolute result reaches `CreateProcessW(None, command, …)` (`isolation.py:1976`) via `list2cmdline` (`isolation.py:1927`). An absolute first token means no search [DOC] |
| 2 | What argv[0] actually is | Windows | If `which` returns an npm shim (`claude.cmd`), `CreateProcess` runs it through `cmd.exe` [DOC], and the shim then finds `node` itself (next to the shim, else on `PATH`) [DOC: npm cmd-shim]. A native `claude.exe` needs no Node. Which one this machine has is not read here | Process start | **[UNVERIFIED]**: which install exists, and whether a `.cmd` first token works under AppContainer at all |
| 3 | The hook interpreter and script | Core writes them; the CLI runs them | `hook_settings` = `(sys.executable, '-I', HOOK)` for isolated, `(sys.executable, HOOK)` otherwise (`manager.py:229`); `HOOK` is this repo's `harnesses/hook.py` (`manager.py:41-42`). The adapter quotes each part into one `command` string in `res/settings.json` (`adapter.py:126-130`) [CODE] | Every process (`_settings` is called from `argv`, `adapter.py:138`) | The interpreter is Core's real install and the script is the repo file: exactly the two paths `default_plan` names as planned-only rows (`isolation.py:1134-1135`) |
| 4 | How the CLI executes that `command` string | The CLI | Through its shell; on Windows the CLI uses Git Bash [DOC: Claude Code docs]. The command's first word is an absolute quoted path, so the shell does no `PATH` lookup for it [DOC] | Every hook event | **[UNVERIFIED]**: which shell, how the CLI finds it (`PATH`, or a CLI-specific variable), and whether it starts under AppContainer |
| 5 | The hook's own children | — | None: `hook.py` imports only `json`, `os`, `re`, `sys`, `time` (`hook.py:32-36`) and starts no process [CODE] | — | — |
| 6 | Tools a turn runs (git, node, npm, python, shell built-ins) | The CLI's shell | The **child's** `PATH` and `PATHEXT` from the environment block (`base.py:316-321`, written at `isolation.py:1965`) [CODE]; lookup rules [DOC] | Per tool call | T-033's interim `PATH` filter, labelled unverified (T-031 Correction §2) |
| 7 | DLLs of every process | Windows loader | KnownDLLs, the application directory, the system directories, then (with SafeDllSearchMode, the default) the current directory, then `PATH` [DOC] | Process start and every `LoadLibrary` | The hook's application directory is Core's real Python install; its current directory is the execution workdir, which the execution writes [CODE: `cwd=spec.workdir`, `base.py:334`] |
| 8 | Python's `sys.path` | The interpreter | `._pth` next to the executable if present; else `PYTHONHOME` (ignored under `-I`/`-E`); else the landmark search from the executable's directory (`Lib\os.py`, `pythonXY.zip`); `pyvenv.cfg` next to or above the executable; registry `PythonCore` keys, of which "application paths" are always read when no `._pth` exists [DOC] | Interpreter start | `-I` drops the environment, the user site and the script directory [DOC]; the rest still applies |
| 9 | Python extension modules (`.pyd`) | CPython | Since 3.8, loaded with secure search flags: the application and system directories plus directories added by `os.add_dll_directory`, never the current directory or `PATH` [DOC] | Import | Same |
| 10 | The fake harness's hook | The fake agent | `subprocess.run(cmd, …)` on the JSON argv in `ARCHEUS_HOOK_CMD` (`fake_agent.py:114`, `:156`; set at `fake.py:103-105`) [CODE] | Per fake tool call | Same tuple as #3, so a staged pair is exercised by the existing fake path without new seams |

Two consequences:
- **The child's `PATH` never chooses the CLI or the hook interpreter.** Both are absolute (rows 1 and 3). `PATH` matters for row 2 (a shim finding `node`), row 4 (finding the shell, if `PATH` is how), row 6 (tools) and row 7 (DLL fallback).
- **On the owner's machine Core's interpreter is a per-user install under the user profile** (the `Python310` of `CLAUDE.md`'s incident bullet). Under AppContainer that tree is not readable without a grant, and a grant on it is exactly the 2026-10-08 incident. So for the hook, staging a copy is not an optimisation; it is the only route that never writes an ACE on a shared tree.

## 2. The hook's runtime closure under `python -I`

The spike ran a copied runtime successfully [SPIKE: `HANDOFF-PV20-SPIKE.md:37-39`], but it located its stdlib through `PYTHONHOME` and `PYTHONPATH` in the environment (`.spike/spike_host.py:328-329`). Under `-I` both are ignored [DOC], so the staged copy must find its stdlib from its own layout.

| Item | Why it is needed | Source of the claim |
|---|---|---|
| `python.exe` | The interpreter the hook command names | [CODE] row 3 |
| `python3.dll`, `python310.dll` (the versioned name follows Core's interpreter) | `python.exe` imports the versioned DLL; the stable-ABI `python3.dll` is loaded by extension modules | [DOC]; copied by the spike [SPIKE: `spike_host.py:130-136`] |
| `vcruntime140.dll`, `vcruntime140_1.dll` | The C runtime `python310.dll` links against; found in the application directory before the system directories | [DOC]; copied by the spike |
| `Lib\` minus `site-packages`, `test`, `idlelib`, `ensurepip`, `venv`, `tkinter`, `turtledemo`, `lib2to3`, `__pycache__` | The stdlib, including `encodings` (needed at every start) and the modules the hook imports (`json`, `re` and their pure-Python parts) | [SPIKE: `spike_host.py:124-128`, the "slim stdlib cache"]; the exact minimum is [UNVERIFIED] |
| `DLLs\` | Extension modules. Whether the hook's five imports need any of them, or whether `_json`, `_sre` and the rest are built into `python310.dll` on this build, is not read here | [SPIKE] copied it; necessity [UNVERIFIED] |
| `python310._pth` (written by Core, not copied) | Pins `sys.path` to the stage's own `Lib`, `DLLs` (and zip, if used); with a `._pth` present the registry and the environment are ignored and `site` is not imported unless the file says `import site` | [DOC]. Recommended (§4): it removes the registry "application paths" and `sitecustomize` from the hook's startup, which `-I` alone does not |
| `hook.py` | The script | [CODE] |
| no `pyvenv.cfg` anywhere in or above the stage | Its presence switches the interpreter to venv mode with a `home =` pointing elsewhere | [DOC]; a test asserts absence |
| no `cmd.exe`, `ping.exe` | The spike copied them for its grandchild tests (`spike_host.py:137-139`); the hook starts no process (row 5) | [CODE] |

What `python -I` still reads even with the closure above [DOC unless marked]:
- the `._pth` file (that is why Core writes it);
- `pyvenv.cfg` next to or one level above the executable (none, by construction and test);
- without a `._pth`: the registry `PythonCore\3.10\PythonPath` application keys under HKCU and HKLM. Whether an AppContainer can read those keys is [UNVERIFIED];
- `__pycache__` beside each module, which it reads and tries to write; a failed write is ignored by CPython [DOC]. Precompiling at staging is an optimisation, not needed for correctness;
- the system directories for DLLs it does not find in its own directory (row 7).

Core's interpreter may itself be a venv launcher. Staging must copy from `sys.base_prefix` (the real install) and never from `dirname(sys.executable)` when the two differ. The hook command names the staged `python.exe` explicitly, whatever launcher Core itself runs under (`pythonw.exe` included).

## 3. Placement: Core-owned, never class 7

| Candidate place | Execution access (target) | Verdict |
|---|---|---|
| `<ARCHEUS_HOME>/runtime/<digest>/` (new) | read/execute only, once S2-G grants it (R7: "grants on shared runtime material are read/execute only, and that material holds no user secrets", ADR-0053:163-166; PV-20 design:74-79) | **Recommended** |
| `run/exec/<id>/own/…` (class 7) | read/write | Rejected: the execution could replace the interpreter or the hook, which is the gate on every tool call |
| anywhere under `run/` | — | Rejected: `default_plan` names `run_dir()` as Core-owned state that must stay ungranted (`core_state=run_dir()`, `isolation.py:1144`; the separation check at `isolation.py:224-226`). A stage there would make that row ambiguous |
| Core's interpreter install or this repository | — | Rejected: the incident rule (`CLAUDE.md`, "BLACK Qt WINDOW" bullet; the comment at `isolation.py:1129-1132`) |

`runtime` becomes a new `V1_OWNED` entry (`paths.py:28-29`), so a reset knows it is V1's and the Qt-owned entries stay untouched.

### 3.1 Shared, content-addressed, write-once (T-017 Q2, answered as a recommendation)

- **One stage per content, shared by executions.** R7 permits shared read/execute material that holds no user secrets; the stage holds Python's stdlib and Archeus's own hook, neither of which is a secret. A per-execution copy would cost the whole closure (tens of MB) and its copy time on every isolated spawn for no boundary gain, because the target access is read/execute either way. Reversible: the stager can be pointed at a per-execution directory later without changing anything that consumes it.
- **Name = digest.** The directory name is the SHA-256 of the manifest (relative path and SHA-256 of every file, sorted). A changed `hook.py` or a Python upgrade yields a new directory; nothing is ever edited in place.
- **Write-once.** Staging writes into a temporary sibling, verifies it against the manifest just computed, then renames it to `<digest>`. A partial stage never carries a digest name. If `<digest>` already exists, it is reused after verification; a mismatch is a refusal (below), never a repair.
- **Copies, never links.** `shutil.copy2`-style copies of file data; no hardlink, symlink, junction or `CopyFile` flag that carries the source's security. A copied file takes the destination's inherited ACL, not the source's [DOC: `CopyFile` does not copy the security descriptor; on Core's Python 3.10 `shutil.copyfile` copies bytes]. Tests assert `st_nlink == 1` and a file identity different from the source.
- **Verified before every isolated spawn.** The spawn re-hashes the stage against its manifest. This catches a change between staging and spawn. It does not stop a same-user process changing a file during a run: everything under `ARCHEUS_HOME` is writable by the user and by any process running as the user (§7).
- **Retention: keep everything.** No stage is ever deleted implicitly (board guidance, 2026-10-12). Cleanup, if ever, is its own card.
- **Failure.** Staging or verification failing refuses the isolated spawn before the workspace is chosen, with the existing uncharged `binding` stop reason, the same refusal an isolation-establishment failure takes (`manager.py:270-279` at `7675095` holds that branch). Nothing falls back to Core's real interpreter.

### 3.2 Lifetime against executions

- **First process and resume** use whatever stage the current Core content hashes to. A Core upgrade between a pause and its resume gives the resumed process the new hook, exactly as an ordinary resume already gets the current repo `hook.py` today [CODE: `HOOK` is read from the running Core]. If the owner wants a resume pinned to its first stage, that needs a recorded digest, which is T-035's persistence ground; not proposed here.
- **Hand-off continuation and retry** are new executions and use the current stage.
- **Teardown** of an execution never touches the stage (it is not the execution's).

## 4. Recommended reversible defaults (not owner questions)

1. Stage under `<ARCHEUS_HOME>/runtime/<digest>/`, shared and content-addressed, keep-all (§3).
2. Write `python310._pth` (named after the copied versioned DLL) listing only the stage's `Lib` and `DLLs`, with no `import site` line.
3. Copy the spike's slim closure (§2 table) rather than computing a minimal one now; shrinking it is a later measurement.
4. Verify the full manifest on every isolated spawn; replace with a cheaper check only if a measurement shows the cost matters.
5. Stage lazily on the first isolated spawn that needs it, and refuse with `binding` if staging fails.
6. The hook command names the staged `python.exe`, `-I` and the staged `hook.py`, all absolute (T-032 unchanged otherwise).
7. Core-built `PATH` (E3, §5): `SystemRoot\System32` and `SystemRoot` only, plus directories a later accepted card stages or approves. Nothing falls back to Core's `PATH`.

## 5. Core-built `PATH` and what the CLI needs

| Need | Known? | Notes |
|---|---|---|
| The hook interpreter | No `PATH` entry needed | Absolute in the command (§1 row 3) |
| The CLI binary | No `PATH` entry needed for argv[0] | Resolved by Core (§1 row 1). If it is a `.cmd` shim, its `node` lookup may need `PATH` (§1 row 2) [UNVERIFIED] |
| A POSIX shell for hooks and the Bash tool | **Unknown** | Git Bash on Windows [DOC: Claude Code]; how the CLI locates it (`PATH`, `CLAUDE_CODE_GIT_BASH_PATH` or another variable) is [UNVERIFIED]. T-031 lists a CLI-specific shell variable as unknown |
| git for the execution's own repository | **Unknown** | A1/A5 make it the execution's own git (T-030); where its binaries come from is open |
| node, npm, python for the task's own tools | **Unknown** | Depends on the task |
| `cmd.exe` | Derived (`ComSpec`, T-031 Correction §1) | Starting it runs the `AutoRun` registry command unless `/D` is given [DOC]; whether the CLI passes `/D`, and whether AppContainer reads that key, is [UNVERIFIED] |

Whether admin-installed tools under `C:\Program Files` (Git for Windows, Node) are already readable by every AppContainer through the `ALL APPLICATION PACKAGES` ACE, as the spike observed for System32 [SPIKE: `HANDOFF-PV20-SPIKE.md:38-39`], is [UNVERIFIED] and decides owner question 1: if they are, using them needs no ACL write at all; if not, they must be staged like the hook, and granting their real install directories is the incident class and is never an option.

## 6. Search and startup limits that staging, `-I` and environment filtering do not remove

| Mechanism | What still applies | Addressed by |
|---|---|---|
| DLL search order (§1 row 7) | After the application and system directories, the current directory (the execution workdir, execution-writable) and `PATH` [DOC]. A DLL the stage lacks could be planted there | Only partly: a complete closure in the stage's application directory means the loader stops before the current directory. Completeness is [UNVERIFIED]. Process-level mitigations (`SetDefaultDllDirectories`, a process mitigation policy) would be new native calls and a separate card |
| KnownDLLs | Always loaded from System32 [DOC] | Not an attack surface for the execution; listed for completeness |
| `PATHEXT` and shell command lookup | Decides which file a bare tool name runs [DOC] | E3's `PATH`; `PATHEXT` stays a T-031 candidate name |
| Registry (`PythonCore`, `Command Processor\AutoRun`) | Read by the interpreter without a `._pth`, and by `cmd.exe` without `/D` [DOC] | The `._pth` (default 2) for the hook. `cmd.exe`: not addressed. AppContainer registry visibility [UNVERIFIED] |
| Node module resolution | `node_modules` up the script's own directories; global folders under `HOME` (`.node_modules`, `.node_libraries`) [DOC] | Not needed: with `HOME` in class 7 (T-033), the execution can influence its **own** Node process, which is already the untrusted execution. Only Core-provided components that enforce policy (the hook) need integrity against the execution, and the hook is Python |
| git configuration under `HOME` | The execution's own git reads `<home>\.gitconfig` (execution-writable under T-033) [DOC] | Same reasoning: it is the execution's own tool. Core's git runner has its own pinned environment (T-030 W6), never this one |
| Same-user tampering with the stage | Any process running as the user can write under `ARCHEUS_HOME` | Not addressed. Manifest verification catches it before a spawn, not during a run. Only an ACL that denies the user write on the stage would, and the owner has not decided creator authority (T-004) |
| The execution writing the stage | Under AppContainer, nothing grants it write anywhere outside its classes; once S2-G grants read/execute, it can read the stage | The ACL, which is S2-G. Without S2-G there is no grant at all, so the stage is simply unreadable to the execution and isolated dispatch stays impossible (condition 2, `isolation.py:121-124`) |

## 7. What copying addresses, and what it does not

**Addresses:**
- The 2026-10-08 incident class: Core never needs to grant anything on its own Python install or on this repository, because the material the execution needs exists as a Core-owned tree that S2-G can grant without touching anything shared.
- `default_plan`'s two planned-only rows stop naming shared trees (`isolation.py:1134-1135`).
- With `-I` and the `._pth`, the hook's startup no longer reads the environment, the user site, `sitecustomize` or the registry's application paths [DOC].

**Does not:**
- make the stage immutable to the execution (that is S2-G's read/execute ACE) or to other same-user processes (that would need creator authority, T-004);
- prove the closure complete, or that it starts under AppContainer with `-I` and a `._pth` (the spike used environment variables instead) [UNVERIFIED];
- confine DLL search (§6);
- say anything about the CLI, Node, shells or git (§5);
- prove CLI compatibility with any of this.

## 8. Proposed cards

**C4a · Stage the hook runtime (no ACL, no wiring).**
- Files:
  - `archeus/infra/paths.py`: `runtime_dir()` = `<ARCHEUS_HOME>/runtime`, and `'runtime'` added to `V1_OWNED`. Serialise after T-033, which edits the same file.
  - `archeus/node/staging.py` (new, small): `stage(source_root, hook_path, dest_root)` returns the stage directory, its `python.exe`, its `hook.py` and its digest; `verify(stage_dir)`. Copy closure per §2, `._pth` writer, manifest, temp-then-rename. Copies only; no ACL call (the existing static gate covers the new module automatically).
  - `tests/v1/unit/test_pv20_runtime_stage.py` (new).
- Fake tests, on a synthetic runtime tree in `tmp_path` (fake `python.exe`, `python310.dll`, `vcruntime140.dll`, `Lib/os.py`, `Lib/encodings/__init__.py`, `Lib/site-packages/evil.py`, `Lib/test/x.py`, `DLLs/x.pyd`, a stray `pyvenv.cfg` in the source):
  - every staged file is a copy: `st_nlink == 1` and a file identity different from its source;
  - everything written is under `dest_root`; the source tree is byte-identical and unmodified afterwards;
  - excluded directories and `pyvenv.cfg` are absent from the stage;
  - `python310._pth` exists, lists only the stage's `Lib` and `DLLs`, and has no `import site`;
  - the manifest covers every staged file; the digest is stable for the same input and changes when `hook.py` changes;
  - `verify` fails on a modified, added and removed file;
  - an existing digest directory is reused, not rewritten; a leftover temporary directory from an interrupted stage is never returned;
  - copying from a venv-shaped source uses the base install (a synthetic `base_prefix` argument).
- Mutants: hardlink instead of copy; drop the exclusion list; omit the `._pth`; write `import site`; rename before verify; skip `verify` on reuse.

**C4b · Wire the stage into isolated spawns.**
- Files: `archeus/core/execution/manager.py` (`_spawn`: stage-or-verify after the isolation decision and before `_workspace`; isolated `hook_settings` = staged `python.exe`, `-I`, staged `hook.py`; failure refuses with `binding`); `archeus/node/isolation.py` (`default_plan`'s `runtime` and `hook` rows name the stage directory; still planned only); `tests/v1/unit/test_execution_units.py` (the existing `_spawn` rig); `tests/v1/unit/test_pv20_isolation.py` (`default_plan` rows).
- Fake tests: the isolated command names three paths inside `runtime_dir()` and none inside `sys.base_prefix` or the repository; ordinary is unchanged; staging failure refuses with `binding` before the workspace, inventory, `prepare_process` and spawn; resume re-verifies; `default_plan`'s rows lie outside `dirname(sys.executable)` and the repository (T-017's `test_default_plan_names_no_path_in_the_python_install_or_the_repo`); the fake harness path runs the staged tuple unchanged (§1 row 10).
- Depends on C4a, T-032 (done) and T-033 (same `manager.py`).

**E3 · Core-built `PATH`.** Default 7 (§4), replacing T-033's interim filter. Blocked on owner question 1 and on the gated run, because what it must add is unknown (§5).

**Separately gated, not a code card:** a real-runtime run under an `auth:` naming the operation (T-008's kind) to establish: that the staged interpreter starts under AppContainer with `-I` and the `._pth`, with only the stage and System32 readable; which modules and DLLs it actually loads; whether `C:\Program Files` tool directories are readable through `ALL APPLICATION PACKAGES`; how the CLI finds its shell; and which install of the CLI exists and what it needs.

## 9. Owner questions

1. **Toolchain for isolated turns (the CLI itself, Node, a shell, git).** Prefer admin-installed copies that the gated run shows are already AppContainer-readable without any ACL write, stage Core-owned copies of them like the hook, or both? Either way, a grant on their real install directories is never an option. E3 waits on this answer and on the gated run.
2. **The gated real-runtime run (§8).** Authorize it as a separate card naming the operations, or keep C4a/C4b fake-only and leave the stage unproven until S2-G?

T-017's question 2 (shared versus per-execution staged runtime) is answered here as reversible default 1, within R7; the owner can still overrule it.
