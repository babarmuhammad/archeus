# T-046 · K1: Core-owned Git store and pinned runner — implementation contract

Analysis only (Claude fork, 2026-10-13). Source read at `9e4443f` in `D:\archeus-pv20-s2-l` by file reads and searches. Nothing was run in any repository, and nothing was created, transferred, imported or copied. No app, test or canonical document was edited. Git documentation was read from git-scm.com (it documents Git 2.56.0). That text is untrusted data, and the installed Git version was **not** checked. Every pin below is a **CANDIDATE** unless it is marked as backed by the documentation, and even that backing is documentation, not observed behaviour.

## 1. What exists today

**One runner, unpinned.** Every Git call Core makes goes through `claude_sessions/proc.py`:
- `run` (`:47-73`) and its wrapper `git` (`:76-81`).
- `args[0]` is the bare name `'git'`, which the OS search resolves. The absolute executable is never resolved or recorded.
- `env=None` means Core's whole environment is inherited, `GIT_*` included.
- Only `cwd` and `timeout` are passed.
- Decoding, the console flag and stdin are pinned (`:63-68`). Config and hooks are not.

The only `-c` flags anywhere are the identity triple: `local.py:418-419` for the snapshot and `:475-476` for the merge.

**Helpers K1 can reuse:**
- `archeus/infra/paths.py`: `archeus_home()` (`:36`). The `V1_OWNED` declaration (`:28-29`) is tied to the canonical ownership table by `tests/v1/unit/test_paths.py:115-133`. `ExecPaths` refuses an ill-formed id before it becomes a directory name (`:140-145`).
- `archeus/node/staging.py`: the precedent for a Core-owned, keep-all directory under `ARCHEUS_HOME`. `_entry`/`_plain` (`:38-50`, `:144`) refuse links, junctions and reparse points with `os.lstat`, narrowing a same-user swap without closing it. The module deletes nothing.
- `archeus/infra/artifacts/store.py` (`put`/`get`, `:30-45`): content-addressed blobs. It is not a Git store; T-030 §3.1 listed it only as an alternative.
- `CORE_GIT_NAME`/`CORE_GIT_EMAIL` (`local.py:31`): Core's Git identity.

## 2. Inventory: every Git command Core runs at 9e4443f

The same authority applies to every row:
- **Executable:** bare `git` found by the OS search.
- **Environment:** Core's own, inherited.
- **Config:** system, global (`~/.gitconfig`, `$XDG_CONFIG_HOME/git/config`), the repository's local config and `config.worktree`, plus any `GIT_CONFIG_COUNT`/`KEY`/`VALUE` or `GIT_CONFIG_PARAMETERS` in Core's environment. The documentation calls these the system, global, local, worktree and command scopes (git-config FILES, SCOPES). Includes are followed when searching all config files (git-config "Includes").
- **Discovery:** the repository is found from `cwd`, unless Core's environment carries `GIT_DIR`/`GIT_WORK_TREE`, which redirect it (git(1) ENVIRONMENT).

The "Honoured beyond config" column is documented Git behaviour, recalled. None of it was executed or re-read in this pass, so all of it is **UNVERIFIED** here.

| # | Site (caller → node) | Command | cwd | Honoured beyond config (UNVERIFIED) |
|---|---|---|---|---|
| G1 | `manager.py:381` → `local.py:288` | `rev-parse --abbrev-ref HEAD` | project root (user) | replace refs |
| G2 | `manager.py:391` → `local.py:452`/`:403` | `rev-parse --verify -q refs/heads/<b>^{commit}` | user root | replace refs |
| G3 | `manager.py:392` → `local.py:365,369,373` | `branch_exists`, `merge-base --is-ancestor`, `worktree add -b/-B` | user root | post-checkout hook, smudge/LFS filters, fsmonitor, submodule config |
| G4 | `manager.py:489,491` → `local.py:288,298` | `rev-parse`, `remote -v` | execution workdir (ordinary; known-isolated skipped since 57a87fd) | includes, `url.*.insteadOf` rewriting the hosts reported |
| G5 | `manager.py:598` → `local.py:320` | `diff --stat HEAD` | execution workdir (ordinary and legacy-None/L1) | fsmonitor, external diff/textconv (UNVERIFIED for `--stat`), index refresh running clean filters |
| G6 | `manager.py:601` → `local.py:336-344` | `--no-optional-locks` `rev-parse`, `diff --binary HEAD`, `ls-files --others --exclude-standard -z`, `hash-object --stdin-paths` | execution workdir | clean filters (`hash-object` without `--no-filters`), fsmonitor, the execution's ignore rules |
| G7 | `worker.py:180,229,272,298,331,337,367` → `local.py:398` | `rev-parse --verify -q HEAD` | workdir, mission worktree, or user root (`:337`) | replace refs |
| G8 | `worker.py:183,230` → `local.py:410-411` | `status --porcelain=v1` | workdir / workspace | fsmonitor, clean filters on racy entries, submodule status |
| G9 | `worker.py:184` → `local.py:418-421` | `add -A`; `commit -q --no-verify` | task workdir | clean filters, LFS; `--no-verify` skips pre-commit and commit-msg only, so post-commit and reference-transaction run |
| G10 | `worker.py:187-188,295` → `local.py:430` | `merge-base` | user root | replace refs |
| G11 | `worker.py:299` → `local.py:435` | `merge-base --is-ancestor` | user root | replace refs |
| G12 | `evidence.py:100`, `worker.py:381` → `local.py:441` | `diff --numstat <base> <rev> --` | user root | attributes from the user's work tree (binary, diff driver), textconv (UNVERIFIED for numstat) |
| G13 | `worker.py:296` → `local.py:461-463,368-373` | `worktree add` (mission) | user root | as G3 |
| G14 | `worker.py:302` → `local.py:477,483,484` | `merge --no-ff --no-edit`; `diff --name-only --diff-filter=U`; `merge --abort` | mission worktree | merge drivers chosen by in-tree attributes (execution-derived after a merge), smudge filters, pre-merge-commit/commit-msg (no `--no-verify`), post-merge, reference-transaction, rerere |
| G15 | `worker.py:308` → `local.py:385,388` | `worktree list --porcelain`; `worktree remove --force` | user root | — |
| G16 | `world/worker.py:69,144` → `inspection.py:94` | `rev-parse HEAD`, a fallback after a file-only read (`:58-93`) | registered repository | replace refs |
| G17 | `application/world.py:74` → `inspection.py:258` | `status --porcelain` | project root | fsmonitor, clean filters |

Not Git runs: `canonical.py:162` (`_git`) only classifies an agent's command line. `git_numstat`'s check wrapper is `evidence.py:94-108`.

## 3. Hazards a pin must cover

**Executable.** An unqualified `git` is resolved by `CreateProcess`'s own search order on Windows. Which directories that includes under Python 3.10 with `cwd=` is **UNVERIFIED** here. Candidate: resolve one absolute path once, record it, and never pass a bare name.

**Environment leakage.** These variables are backed by the documentation (git(1) ENVIRONMENT):
- `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY` and `GIT_ALTERNATE_OBJECT_DIRECTORIES` redirect the repository, its index or its objects.
- `GIT_CONFIG_COUNT` with `GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>` adds command-scope (protected) configuration (git-config ENVIRONMENT).
- `GIT_SSH_COMMAND` and `GIT_ASKPASS` name programs Git will run.
- `GIT_EXEC_PATH` chooses where Git finds its own subcommands.

Today any of these in Core's environment reaches every row in §2. Candidate: build the child environment from a short allowlist (`SYSTEMROOT`, `TEMP`/`TMP`, `PATH` reduced to the git directory) and drop every inherited `GIT_*`.

**Config scopes:**
- *Doc-backed:* `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` set to a file keeps `$HOME/.gitconfig`, `$XDG_CONFIG_HOME/git/config` and the build-time system file from being read. `GIT_CONFIG_NOSYSTEM` skips the system file (git(1)).
- *Candidate:* `HOME` and `XDG_CONFIG_HOME` pointing at an empty Core directory, as a second layer.
- A repository's own local config cannot be excluded by an environment variable. It is excluded only by never running in that repository, which is the store's whole point. Includes in a local config are followed (git-config "Includes"; no repository-scope restriction is stated).

**Repository-local and in-tree hazards** (candidate counters; the option semantics are recalled and **UNVERIFIED**, except where marked doc-backed):
- Hooks, including `reference-transaction` on every ref update and `post-checkout`/`post-merge`/`post-commit`: `-c core.hooksPath=<empty Core dir>` plus a bare store made with `--template=<empty Core dir>`.
- fsmonitor: `-c core.fsmonitor=false`. Avoiding work-tree commands in the store also avoids it.
- Clean/smudge/process filters and LFS: write blobs with `hash-object -w --no-filters`; never check out or use `add` inside the store; define no `filter.*`.
- Diff and merge drivers, textconv, external diff: `--no-ext-diff --no-textconv` on every diff; `GIT_EXTERNAL_DIFF` dropped with the environment.
- Attributes:
  - `info/attributes` in a bare store must be absent.
  - `core.attributesFile` pinned to an empty file.
  - `--attr-source=<empty tree>` is doc-backed as equivalent to `GIT_ATTR_SOURCE`.
  - A bare repository may by default read attributes from `HEAD`'s tree (`attr.tree`, recent Git). That is **UNVERIFIED**, and it is the hazard to settle first: a store whose `HEAD` names execution-derived content would supply its own `.gitattributes`.
  - Candidate: store `HEAD` stays an unborn Core ref, *and* attributes come from the empty tree.
- Replace refs: `--no-replace-objects`, doc-backed as equivalent to `GIT_NO_REPLACE_OBJECTS`.
- Alternates and `commondir`: `objects/info/alternates`, `commondir` and `config.worktree` must be absent from the store, checked on every open.
- Submodules and gitlinks (mode 160000), symlinks (120000), `.gitmodules`, `.lfsconfig`: inert in a bare store as long as nothing checks out, recurses or reads attributes from them. Candidate: `-c submodule.recurse=false`, `fetch --no-recurse-submodules`.
- Transport:
  - *Doc-backed:* `GIT_ALLOW_PROTOCOL=file` behaves as `protocol.allow=never` with only the listed protocols allowed. `GIT_PROTOCOL_FROM_USER=0` refuses `user`-state protocols. `GIT_TERMINAL_PROMPT=0` stops prompts.
  - *UNVERIFIED:* whether `file` covers bare local paths as well as `file://`.
- `safe.directory`: never set by the pin. A `-c` value is command scope, which the documentation calls protected configuration (git-config SCOPES), so `-c safe.directory=*` would lift Git's ownership check on a user repository.
- GC and maintenance: candidate `-c gc.auto=0 -c maintenance.auto=false`, plus `--no-auto-gc` on fetch, to keep keep-all.

**Path and link assumptions:**
- The store path comes from `project_id`, refused unless `ids.is_id(project_id, 'project')`, as `ExecPaths` does.
- The `repos` directory and the store must be plain directories by `staging._entry`'s test before every use. This narrows a time-of-check race; it does not close it.
- Every Git argument path (`--git-dir`, `cwd`, any `--work-tree`) must lie outside these, by a structural `commonpath` refusal like `tests/v1/conftest.py`'s install guard:
  - `run/exec/*` (class 1-7, `paths.py:131-159`);
  - `worktrees/*`;
  - every execution workdir recorded in the database.

**Object provenance.** An object id does not say where an object came from. In K1 provenance is the **ref** naming it:
- `refs/archeus/exec/<execution_id>/seed` is copied from the user's repository;
- `.../import` is written by K3 as data.

A commit Core writes there is plumbing (`commit-tree`, `update-ref`) under Core's identity, never porcelain. Objects fetched from the user's repository include whatever earlier merges brought into it, execution-derived content included, so the store treats every object as hostile data.

## 4. Proposed K1: one store, one runner, one pin

**Location and ownership.** `paths.repo_store(project_id)` returns `<ARCHEUS_HOME>/repos/<project_id>.git`. `'repos'` is added to `V1_OWNED`. That needs an additive canonical row in `docs/architecture/target-architecture.md`'s ownership table (`:197-213`, enforced by `test_paths.py:115-133`), plus a statement that the reset paragraph in `migration-plan.md` never names it, as `test_pv20_runtime_stage.py:653-660` already pins for `runtime/`. The store is never granted, never a workdir and never deleted (keep-all; cleanup is a separate card).

**Runner.** A single `LocalNode.store_git(args, *, git_dir, stdin=None, timeout)` in `archeus/node/local.py`, where every other node side effect lives. It is the only place the pin is built:
- **argv:** `[<absolute git>, '--git-dir', git_dir, '--no-replace-objects', '--attr-source', <empty tree>, '-c', 'core.hooksPath=<empty Core dir>', '-c', 'core.fsmonitor=false', '-c', 'core.attributesFile=<empty Core file>', '-c', 'submodule.recurse=false', '-c', 'gc.auto=0', '-c', 'maintenance.auto=false', '-c', 'commit.gpgsign=false', '-c', 'user.name=Archeus', '-c', 'user.email=archeus@localhost', *args]`. The empty tree is the well-known empty-tree id for the store's hash algorithm, or the output of `mktree` on empty input; which one is **UNVERIFIED**.
- **env:** the allowlist above, plus:
  - `GIT_CONFIG_NOSYSTEM=1`;
  - `GIT_CONFIG_SYSTEM`/`GIT_CONFIG_GLOBAL` set to one empty Core file;
  - `HOME`/`XDG_CONFIG_HOME` set to an empty Core directory;
  - `GIT_TERMINAL_PROMPT=0`, `GIT_ALLOW_PROTOCOL=file`, `GIT_PROTOCOL_FROM_USER=0`, `GIT_NO_REPLACE_OBJECTS=1`.
- **cwd:** the store itself.
- **Refusal before any spawn:** `git_dir` is not this project's store, or any path argument falls inside an execution area (§3).

The empty files and directories live under `repos/.pin/`. They are made and checked by Core, and the runner refuses to run if any of them is not empty.

**Store operations K1 ships** (the rest is K2, K3 and K5b's, through the same runner):
1. `store_open(project_id)`:
   - creates the store if absent: `init --bare --template=<empty Core dir>` under the pin, with `cwd` the parent;
   - then verifies the store as it opens it: config bytes equal Core's recorded bytes; no `hooks/` content, `info/attributes`, `objects/info/alternates`, `commondir` or `config.worktree`; `HEAD` the unborn `refs/archeus/none`.
2. `store_fetch(project_id, root, rev_name, expect, ref)`, the C2 transfer:
   - `fetch --no-tags --no-recurse-submodules --no-write-fetch-head --no-auto-gc <root> +<rev_name>:refs/archeus/incoming/<ref>`, run in the store;
   - `rev-parse` the incoming ref; it must equal `expect`, the commit id Core resolved, or the call is refused as a lost race;
   - then `update-ref <ref> <expect>`. Nothing is deleted; the incoming ref stays.
   - On the source side, the local transport starts `upload-pack` in the **user's** repository with its local config. Whether the parent's `-c`/environment pins reach that child is **UNVERIFIED**.
3. `store_read(project_id, args)` for plumbing reads only (`rev-parse`, `cat-file`, `ls-tree`, `merge-base`, `diff --numstat --no-ext-diff --no-textconv`). Any subcommand outside a fixed allowlist is refused.

**User-repository reads stay a separate, smaller mode.** C2's `rev-parse <ref>^{commit}` runs with an explicit `--git-dir` (taken from `repos._gitdir(root)`) and the same environment and config pin. The user's local config is still read (§3). Writes into the user's repository (`worktree add`, merge, fetch from the store) are K5b's under owner Q9; K1 does not touch them.

**What K1 does not change.** The G1-G17 legacy calls keep `proc.git`. Retrofitting the pin onto ordinary executions would silently turn off the user's own hooks and filters in their own worktrees, which is a behaviour change for K5b/Q9 to decide. "No duplicate pins" is enforced statically instead: one function builds the pin, and an AST test fails on any other `GIT_CONFIG_*`, `core.hooksPath` or store path literal in `archeus/`.

## 5. Bounded manifest for the K1 implementation card

- `archeus/infra/paths.py`: `repos_dir()`, `repo_store(project_id)`, and `'repos'` in `V1_OWNED`.
- `archeus/node/local.py`: `store_git`, `store_open`, `store_fetch`, `store_read`, the pin constants, and the absolute-executable resolution (once, recorded).
- `docs/architecture/target-architecture.md`: one additive ownership row for `repos/` (canonical, append-only, needs naming in the card's authority).
- `tests/v1/unit/test_repo_store.py` (new, no subprocess): a fake `proc.run` records argv, env and cwd.
- `tests/v1/integration/test_repo_store.py` (new): real Git, in pytest temp only.
- `tests/v1/unit/test_paths.py`: no edit expected; it should pass once the row exists.

## 6. Proposed synthetic tests (described, not written)

**Unit tests (fake `proc.run`, any real spawn fails the test):**
1. The pin is complete:
   - absolute executable;
   - every `-c` and environment pin above;
   - `cwd` is the store.
2. Hostile environment: `GIT_DIR`, `GIT_CONFIG_COUNT=1`/`KEY_0=core.hooksPath`, `GIT_EXTERNAL_DIFF`, `GIT_SSH_COMMAND` and `GIT_EXEC_PATH` are set in `os.environ`, and none reaches the child.
3. Refusal with zero spawns for:
   - `git_dir` or `cwd` inside `ExecPaths(x).work`, inside `worktrees/`, or equal to a project root;
   - an ill-formed `project_id`;
   - a subcommand outside the read allowlist;
   - a non-empty pin file.
4. Static guards: the pin is built in exactly one function, and no other module names `GIT_CONFIG_*` or `repos/`.

**Integration tests (real Git, pytest temp only):**
5. The store as created: bare; empty hooks; no alternates, `info/attributes` or `commondir`; config bytes recorded and re-verified; a planted `objects/info/alternates` makes the next open refuse.
6. Sentinels. Each hazard below would create a sentinel file if honoured, and `store_open` → `store_fetch` → `store_read` (`rev-parse`, `cat-file`, `diff --numstat`) must leave every sentinel uncreated:
   - In a temp **user** repository: `post-checkout`, `post-merge` and `reference-transaction` hooks; a `core.fsmonitor` command; clean/smudge filters named by `.gitattributes`; `diff.external`; a textconv driver; `include.path` to a file setting `core.hooksPath`; a replace ref.
   - In a fake `HOME`/`XDG_CONFIG_HOME`: the same hazards.
   - In the environment: `GIT_CONFIG_COUNT` setting the same.
   - The replaced object's original content is what the store reads.
7. Bare-repository attributes: a store commit whose tree holds a `.gitattributes` naming a sentinel diff driver and textconv. A numstat between it and its parent creates no sentinel. This settles the `attr.tree` question.
8. Lost race: the user's ref moves between Core's resolve and the fetch. The call is refused, the target ref is never written, and the incoming ref is kept.

## 7. Meaningful unknowns

- **Installed Git version:** never checked. `GIT_CONFIG_GLOBAL`, `--attr-source`/`GIT_ATTR_SOURCE` and `attr.tree` all depend on it, and the runner needs a version floor and a way to read the version.
- **Bare-repository default attribute source** (§3), and whether `--attr-source` covers every attribute lookup.
- **Whether pins reach the source-side `upload-pack`** of a local fetch, and whether `GIT_ALLOW_PROTOCOL=file` covers bare paths.
- **Windows executable search order** under Python 3.10 with `cwd=`.
- **Size and time** of fetching a whole user history into the store, and the store's growth under keep-all.
- **Same-user writers:** a process running as the user can rewrite the store or `repos/.pin/` between checks. Plain-directory and empty-file checks narrow that window and do not close it.

**No hostile-content confinement claim.** Git parses fetched and imported objects in Core's own process context, unconfined. A malformed object, pack or path that exploits Git itself is out of reach of every pin here. The pins remove Git's *configured* execution points; they do not make Git a sandbox.

## 8. Owner questions

1. **Authority for the K1 implementation card.**
   - **(A, recommended)** Name in one card:
     - the additive `repos/` ownership row in `target-architecture.md`;
     - real Git in pytest-owned temp repositories for `test_repo_store.py`, as T-045 allows;
     - one `git version` read through the pinned runner with `cwd` set to an empty Core directory, to enforce a version floor.
   - **(B)** Unit tests only, with the integration sentinels deferred to K5b. In that case no pin is ever observed working before merge-back depends on it.
2. **Scope of user-repository reads in K1.**
   - **(A, recommended)** K1 includes the pinned read mode for C2's resolve only (`--git-dir`, global and system config excluded, the user's local config still read). Every write into the user's repository stays with K5b/Q9.
   - **(B)** Store-only K1; C2 keeps `proc.git` until K2.
