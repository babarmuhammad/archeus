# T-049 · K2: bounded seed contract built on candidate K1

Analysis only (Claude fork, 2026-10-13). The reviewed baseline is `5dfac53` in `D:\archeus-pv20-s2-l`. It differs from `9e4443f` only in `tests/v1/integration/test_provenance.py`, so the T-046 citations still hold. Source was read with file reads and searches only. Nothing was run in either checkout: no Git, no seed, archive, clone, copy, content scan or import, no tests, and no native, API, CLI or provider action.

**Candidate K1** (T-048, `D:\archeus-pv20-k1`) is unreviewed. A search there found no `test_repo_store.py`, so nothing of it was read. Everything below depends on the **contract** for K1 (T-046 including Correction C-1013-T046, approved as a candidate in `reviews/T-046-analysis.r2.md`), not on its code. No pin is presumed to work.

## 0. What this note does not do

- It does not lift T-027's refusal. An isolated execution with a project still raises at `manager.py:367-374` ("an isolated execution has no project workspace yet"), and `_spawn` turns that into a charged `workspace` refusal (`:221-226`).
- It enables no seed, import or project, and authorises none of K2-K6.
- It decides none of T-030 §3.3's owner questions. It narrows Q1 (links, seed half) to one choice in §8.
- It does not cover no-project executions. They get no store, seed or import (T-030 C-1012-T030 §2); their workspace stays `ExecPaths(e.id).work` (`manager.py:361-366`).

## 1. Today, at 5dfac53

- **The base is a ref name, resolved by Git at add time and never recorded.** `_workspace` passes the mission branch if `branch_exists(root, mission)`, else the literal `'HEAD'`, to `add_worktree` (`manager.py:390-392`). That runs `git worktree add` in the user's root (`local.py:357-378`). The worker later recomputes a base with `merge-base` at verification time (`worker.py:186-189`).
- **The workspace belongs to the task, not the execution.** Its path is `worktrees/<project>/<mission>/<key>` (`manager.py:387`), and `add_worktree` returns early when the directory exists (`local.py:361-362`). A retry and a hand-off continuation therefore inherit the directory in place.
- **`Execution.workdir` and `.branch` are mutable.** `prepare_process` rewrites both on every preparation, resumes included (`executions.py:127-128`). Only `isolated` is write-once: it is recorded at `process_seq == 0` (`:119`), and a mismatch on a resume is refused uncharged (`:115-118`).
- **Every Git call is unpinned.** It goes through `proc.git`/`proc.run`; T-046 §2 lists G1-G17.
- **K4a (`57a87fd`) already makes a known-isolated execution's end and hook context run no Git** (`manager.py:479-497`, `:558`). One consequence matters here: a known-isolated execution that has a recorded `branch` fails the branch gate on every hook request (`:496-497`). See §7.

## 2. Authority for the base commit

**Rule.** The only base any later step may use for an execution is `Execution.seed_revision`: a commit id, write-once, recorded by `prepare_process` at the first preparation, beside `isolated`. A ref name is never recorded (T-030 C2). Nothing read later replaces it. The `changes` base (T-030 §3.2 default) and the import's parent (C5) both come from it. That includes the user's refs, `e.workdir`, `e.branch` and the workspace's own `.git`.

**Where the id comes from.** In priority order, with the source of each:

| Case | Source of `seed_revision` | Authority |
|---|---|---|
| Hand-off continuation (`handoff_from` set, `work.py:78-91`) | the predecessor's `import_revision` (K3) | a write-once Core record of the predecessor |
| Retry (attempt n+1 of a task in the same plan) | the latest earlier attempt's `import_revision` if any (T-030 §3.2 default), else that attempt's own `seed_revision` | write-once Core records; the user's refs are not re-read |
| First attempt | the user's mission branch `refs/heads/archeus/<mission>^{commit}` if it resolves, else `HEAD^{commit}` | one read under K1's pinned user-repository read mode (T-046 §4, owner Q2(A)), recorded as an id |

**Notes on the first attempt:**
- The mission branch stays a source, rather than only `Mission.integration_head`, because the user resolves a conflict *on* that branch (D13, `retry_merge`). Their commit has to reach the next task.
- **Detached HEAD** records the commit it names.
- **Refusals before anything is written:**
  - an unborn `HEAD` (an empty repository);
  - a root that is not a Git repository (T-016 W5 refuses that before dispatch);
  - a resolve that fails.
- **Object format.** The id is 40 hex characters for SHA-1 or 64 for SHA-256, and must match the store's recorded `object_format` (T-046 C1 step 5). A mismatch refuses.

**Copy into the store.** C2 is `store_fetch` of the resolved id into `refs/archeus/incoming/<execution_id>` and then `refs/archeus/exec/<execution_id>/seed` (T-046 §4). **This has no production authority.** `store_fetch` raises outside tests until source-side and local-transport evidence is accepted (T-046 C1; T-048 card). K2 therefore cannot seed a real project before that evidence exists. Tests use T-048's trusted fixture injection.

## 3. Seed ref ownership

- **Refs.** `refs/archeus/exec/<execution_id>/seed` in `<ARCHEUS_HOME>/repos/<project_id>.git`:
  - written once by Core, by `update-ref`, only after the incoming ref's id equals the resolved id (otherwise refused as a lost race, T-046 §4);
  - never moved or deleted, and the incoming ref is kept too (keep-all);
  - one ref per execution, so a retry or continuation never reuses or moves another execution's seed ref. A seed taken from a predecessor's import points the new execution's seed ref at the same commit, under its own name.
- **The execution never sees the store.** It is never granted and is never a workdir (T-046 §4), and the execution's repository has no remote (§4 step 4).

## 4. The seed: built outside the execution area, then moved in

**The conflict.** K1 refuses any Git argument path, `cwd` included, under `run/exec/*`, `worktrees/*` or a recorded workdir (T-046 §3, enforced before spawn). The class-7 workspace, `ExecPaths(e.id).work` = `run/exec/<id>/own/work` (`paths.py:155`), sits inside that refusal. T-030's S-a seed ran Git in the new execution repository before the first process. Under K1 that is refused, and it should stay refused.

**The resolution.** Core builds the repository in a Core-private staging directory, `<ARCHEUS_HOME>/repos/.seed/<execution_id>/`, and then renames it into place. Both paths are under `ARCHEUS_HOME` (`run_dir`, `paths.py:72-74`), so the rename never crosses a volume. Git never runs with a path under `run/exec`, and it does not run at all once the workspace exists.

**Steps, in order.** Each one is a precondition of the next. Any failure refuses and keeps what exists (keep-all), and never retries with fewer pins:

1. **Fresh-directory check.** Neither `ExecPaths(e.id).work` nor the staging directory exists. Each parent is a plain directory by `staging._entry`'s test (`staging.py:38-47`). A directory that already exists means refuse, never reuse.
2. **Manifest from the store**, in K1 `trusted` mode with `cwd` the store: `ls-tree -r -z -l --full-tree <seed_revision>`. The result is a list of (mode, type, id, size, path). **Bounds and path checks run on this list before a single byte is written** (§5).
3. **Repository skeleton in staging.** This needs a new K1 pin mode, `seed`, with `--git-dir` set to `<staging>/.git`. That changes T-046 C1's mode table and its caller allowlist (rule (b)).
   - `init --template=<repos/.pin/empty/>`.
   - Core writes the `.git/config` bytes itself: `core.symlinks=false`, `core.autocrlf=false`, `core.fileMode=false`, and no remote, `include` or `filter.*`.
   - A shallow fetch of the store's seed ref: `fetch --depth=1 --no-tags --no-recurse-submodules <store> refs/archeus/exec/<id>/seed`. The source is Core's own store, so the `upload-pack` it starts reads Core-sealed config, not the user's.
   - `update-ref refs/heads/archeus/<mission>.<key> <seed_revision>`, then `symbolic-ref HEAD` to that branch.
   - `read-tree <seed_revision>` to build the index only. There is no `-u`, no checkout and no `add`.
4. **Working-tree files, written by Core as data.** Each blob's bytes come from `cat-file --batch` in the store and are written with an exclusive create (`open(path, 'xb')`), so a case collision or a duplicate refuses rather than overwrites. Mode 120000 and 160000 follow §6. Modes come only from the manifest.
5. **Verify staging.**
   - Layout: no `hooks/` content, `info/attributes`, `objects/info/alternates`, `commondir` or `config.worktree`.
   - Config bytes equal Core's, and `.git/shallow` holds exactly `seed_revision`.
   - Every file is plain, with `st_nlink == 1` and no reparse point (as `staging._tree`, `staging.py:172-200`).
   - The file count and total bytes equal the manifest's.
6. **Move it in.** `os.rename(<staging>, ExecPaths(e.id).work)`. The target must be absent.
7. **Record.** `prepare_process(..., seed_revision=<id>)` records it with `isolated` in the same transaction, before spawn, and carries it in `execution.prepared`. A crash between steps 6 and 7 leaves a workspace with no recorded seed. The next pass refuses it (§4 rule c); it never re-seeds over it and never adopts it.

**Rules:**
- **(a)** The execution's HEAD id equals `seed_revision` (a shallow commit). This drops T-030 S-a's new root commit, whose only reason was to avoid a checkout, and no checkout happens here either.
- **(b)** After step 6, Core runs no Git in the workspace for the rest of the execution (T-030 C4, A5). Resume, verification and facts read Core records only.
- **(c)** A workspace whose execution has `process_seq == 0` and no recorded `seed_revision` is unknown provenance and refused (T-046 r2 qualification, applied here).

## 5. Bounds, all checked on the manifest before any write

These are candidate values. The K2 card sets them; breaching any one refuses the seed.
- **Count:** at most 100,000 entries.
- **Bytes:** at most 2 GiB in total, summed from `ls-tree -l` sizes.
- **Depth:** at most 64 path components.
- **Path length:** the full Windows path of a file is at most 259 characters. Long-path support under Python 3.10 is **UNVERIFIED**, so the bound assumes none.
- **Time:** the whole seed must finish within one deadline (candidate 300 s). Each K1 call keeps its own timeout.
- **What is not bounded:** C2's user→store transfer has no size bound before the fetch starts. That is still K1's unknown (T-046 §7).

**Path validation.** Any one of these refuses the whole seed; nothing is skipped:
- the components `.`, `..` or an empty component;
- `\`, `:`, NUL or a control character;
- a Windows reserved device name (`CON`, `NUL`, `COM1` and so on, with or without an extension);
- a trailing dot or space;
- any component equal, case-insensitively, to `.git` or its 8.3 short form `git~1`.

## 6. Links, gitlinks, submodules and nested `.git` in the seed

- **Nested `.git` or `git~1` at any depth:** always refused (§5). This is not a choice.
- **Hardlinks:** none can arise, because Core writes fresh files. Step 5 asserts `st_nlink == 1`.
- **Mode 120000 (symlink)** and **160000 (gitlink)** are owner Q1 (§8). The recommended answer represents both inertly:
  - a symlink becomes a plain file holding the target text, which is what Git for Windows does with `core.symlinks=false`, and its index mode stays 120000;
  - a gitlink becomes an empty directory, with no recursion and no fetch.

  No reparse point is ever created.
- **`.gitmodules`, `.lfsconfig`, `.gitattributes`** are written as data. Core reads none of them.
- **Import-side links are not covered here.** They belong to K3 and the import half of T-030 §3.3 Q1.

## 7. First, resume, retry and hand-off

| Case | Directory | Base | Core Git |
|---|---|---|---|
| First process (`process_seq` 0→1) | new `ExecPaths(e.id).work` | §2 first attempt | store and staging only, before the spawn |
| Resume (PAUSED or AWAITING_APPROVAL, `process_seq` ≥ 1; `_resume`, `manager.py:630-641`) | the same directory: it must exist as a plain directory, else refused with `binding`, uncharged | unchanged: the `seed_revision` passed must equal the recorded one, else refused like `isolated` (`executions.py:115-118`) | none |
| Retry (a new execution, `work.py:84`) | new directory | §2 retry | as on the first process |
| Hand-off continuation | new directory | predecessor's `import_revision` | as on the first process |

**Unresolved, not decided here.**
- **No predecessor import.** A continuation whose predecessor has no `import_revision` cannot be seeded: K3 is absent today, and C-1012-T030 §1 lists the no-import cases. What that task and continuation become, and whether that is charged, is T-030 §3.3 Q2, still open.
  - K2 implements only the refusal point: nothing is seeded and nothing is spawned.
  - Until Q2 is answered, the refusal travels the existing charged `workspace` path (`manager.py:223-226`), labelled as an interim choice.
  - It is unreachable in production while T-027 stands.
- **A missing first-attempt base** (unborn `HEAD`, a non-Git root, a failed resolve, or fetch not authorised) takes the same interim path, with its own reason text.

**Hook gate.** Under K4a a known-isolated execution with a recorded `branch` fails `branch_ok` on every hook request (`manager.py:496-497`). Seeding with the task branch as `Execution.branch` therefore makes a seeded execution unusable until K4b replaces that gate with the Core-recorded label (T-030 §3.2 hook-context default). K6 depends on K4b. K2 does not change the gate.

## 8. Provenance of bytes, modes and attributes; who invokes what

- **Bytes:** exactly the blob bytes of `seed_revision`, read in the store. There is no smudge, `eol`/`text` conversion, `working-tree-encoding` or LFS smudge, so an LFS file stays its pointer text.
- **Mode, executable bit included:** the manifest's mode only. NTFS has no executable bit; the index built by `read-tree` carries 100755, and `core.fileMode=false` keeps the execution's Git from reading it off the filesystem. Core never `chmod`s by attribute.
- **Attributes:** never consulted by Core. The store side runs K1 `trusted` mode with an empty-tree attribute source. Staging runs no checkout and no command that reads work-tree attributes: `read-tree` without `-u` touches only the index.
- **Never invoked:**
  - user or execution hooks: the template is empty, `core.hooksPath` is an empty Core directory, and there is no checkout;
  - checkout or clean/smudge filters, templates, system or global config, `include`, fsmonitor, diff/merge drivers and replace refs: all under K1's environment and `-c` pins (T-046 §4, C1).

  Which of these pins Git actually honours is **CANDIDATE** until T-048's fixtures report.
- **Core-created** (structure Core vouches for):
  - in staging `.git/`: config bytes, `HEAD`, the task-branch ref, `shallow`, the index;
  - in the store: the seed and incoming refs.
- **Copied source content** (hostile data Core only moves): every object fetched into staging, and every working-tree file.
- **Source descriptors:** `seed_revision`, and the manifest derived from its immutable tree in the store. No file list is recorded, because the store's tree is the record.

**At import (K3), nothing written at seed is trusted.**
- From the first process on, the whole workspace is execution-derived, Core's `.git` structure included.
- The import reads it as data only after the quiescence fence (C-1012-T030-2 §1).
- It skips the root `.git`, and diffs against `seed_revision` in the store, never against the workspace's index or HEAD.
- Mutable metadata is never authority. `e.workdir` and `e.branch` are rewritten on each preparation (`executions.py:127-128`), so the import locates the workspace by `ExecPaths(e.id).work`, derived from the id. The base comes from the write-once `seed_revision`.

## 9. Manifest for a K2 card (proposed; authorises nothing)

**Files:**
- `archeus/core/domain/entities.py`:
  - `Execution.seed_revision`, a body field (precedent `inventory_sha256`, `:1010`; no migration);
  - a `_check` for 40 or 64 lowercase hex characters, beside `:1017-1021`.
- `archeus/core/application/executions.py`: `prepare_process(..., seed_revision=None)`, recorded at `process_seq == 0` only. A resume with a different non-None value is refused uncharged, as at `:115-118`. It is added to the `execution.prepared` payload.
- `archeus/node/local.py`:
  - `resolve_base` (K1 pinned user-repository read);
  - `seed_workspace(project_id, execution_id, seed_revision, branch)` (§4 steps 1-6);
  - the `seed` pin mode and the allowlist entries, in K1's `_store_pin`.
- `archeus/infra/paths.py`: `seed_staging(execution_id)` → `repos/.seed/<id>`, under K1's `repos`, so there is no new ownership row.

**Not touched by K2:** `manager.py` (wiring is K6), the worker, `isolation.py`, migrations and the UI.

**Tests**, all on owned temp data:
- `tests/v1/unit/test_execution_units.py`: `seed_revision` is write-once; a resume mismatch is refused uncharged; a legacy None row is untouched.
- `tests/v1/unit/test_repo_store.py`:
  - the `seed` pin's argv, env and cwd, with a refusal when any path is under `run/exec`;
  - path validation, bounds, and the 120000 and 160000 handling, on synthetic `ls-tree` records with zero spawns;
  - the static detector catches a `store_git` call outside the new allowlist.
- `tests/v1/integration/test_repo_store.py` (real Git in pytest temp only, T-048's fixture injection standing in for production fetch):
  - the seeded tree's bytes, HEAD id, `shallow` and layout;
  - `st_nlink == 1`, and no reparse point;
  - hostile `.gitattributes` (filter, eol, encoding), an LFS pointer and `.gitmodules` (`update=!cmd`) in the base each leave their sentinel uncreated, with bytes equal to the blobs;
  - hooks, fsmonitor and global config planted in a temp user repository and a fake `HOME` leave their sentinels uncreated;
  - a pre-existing target or staging directory is refused, and the existing one is left unchanged;
  - a bounds breach refuses before any write;
  - a symlink becomes a plain file, and a gitlink an empty directory (per Q1).

  Which unsafe names `mktree` will accept is **UNVERIFIED**; the unit tests cover the rest.

**Dependencies:**
- K1 (T-048) reviewed, including the pinned user-repository read and the new `seed` mode;
- accepted source-side `store_fetch` evidence before any production seed;
- T-030 §3.3 Q1 (seed half, §8 below);
- K3, for hand-off and retry-from-import;
- K4b, for the hook gate (§7);
- T-030 §3.3 Q2, for the no-import disposition;
- K6 plus the owner's explicit go for enablement;
- T-016 W5, for refusing non-Git roots before dispatch.

## 10. Unverified

- The Git behaviour this plan relies on is recalled, not re-read or run:
  - shallow-fetch semantics into a fresh repository;
  - `read-tree` without `-u` reading no attributes;
  - `cat-file --batch` applying no filter.
- Python 3.10 long-path support, and the reserved-name list's completeness on NTFS.
- Whether `os.rename` of a directory inside `ARCHEUS_HOME` can fail partway on Windows.
- K1 candidate code: not read.
- The user→store transfer size and time.
- Same-user writers between check and rename: narrowed, not closed (as in `staging.py:9-14`).

**No hostile-content confinement claim.** Git parses fetched objects in Core's unconfined process context (T-046 §7).

## Owner questions

1. **Links in the seed (T-030 §3.3 Q1, seed half).**
   - **(A, recommended)** Represent them inertly: a symlink (120000) becomes a plain file holding its target text, with index mode 120000, as Git for Windows writes it with `core.symlinks=false`; a gitlink (160000) becomes an empty directory, never recursed. No reparse point is created, and a project that tracks symlinks or submodules can still be seeded.
   - **(B)** Refuse the whole seed on any 120000 or 160000 entry.

   Nested `.git` and `git~1` entries are refused under either option.
