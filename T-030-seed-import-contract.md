# T-030 · A1/A5 seed and data-only import: one implementation contract

Prepared 2026-10-12. Analysis only: no code, no test, no git seed/clone/archive, no filesystem import, no native or CLI run. Every `file:line` is at worktree `D:\archeus-pv20-s2-l`, commit `0c535e7`, read with `git show 0c535e7:<path>`.

Sources: PV-20 design §3.2 (A1/A5), §3.9 (R4b/A6), §6 items 19-20, §7.5, §8 A1/A5 bullets; ADR-0053 §7 items 2-3, Alternatives, Consequences (A1, A5), "Not decided here"; `T-016-private-workspace-plan.md` (W3, W4, W6, W7, Correction C-1012-T016) and its reviews; `T-017-private-config-plan.md` (C1, §4 Q5, Correction §1); `T-021-isolation-decision-contract.md`; the code named below.

Everything below that says what Core *would* do is a proposal. "Required" means the cited canonical text says so. Mechanics marked **UNVERIFIED** are plausible git behaviour that nobody has checked here.

## 0. What approval of this contract does not do

Approving this note:
- does **not** lift T-027's refusal. Every isolated execution with a project stays refused at `manager.py:342-349` until every card in §9 is implemented, reviewed and accepted, and the owner says so;
- does **not** activate isolated dispatch (`PRODUCTION_DISPATCH_ENABLED = False`, `isolation.py:79`) or any other switch;
- does **not** grant the workspace, the store or anything else to an AppContainer. That is S2-G (T-004, blocked);
- does **not** settle creator authority (T-004), verifier confinement (A6), the provider broker, or the isolated environment contract (T-017 Q5);
- does **not** stand in for Windows or real-CLI evidence (T-008, W-1), or for A5's §8 acceptance run;
- does **not** decide any of the §8 owner questions, the copy or link mechanics, or seed provenance.

## 1. Why seed and import are one contract

They are two halves of the same thing and fail if built apart:

- **Seed without import breaks verification and merge-back.** After the copy seed, a task's commits live only in the execution repository. The verify worker reads git *inside* the workdir: `git_head` (`worker.py:174`), `git_dirty` (`:177`), `git_snapshot` (`:178`), and the post-check `git_head`/`git_dirty` (`:216-217`). Merge-back merges `revision` in a linked worktree of the user's repository (`worker.py:282-289`), which resolves only because a linked worktree shares the user's object store. A seeded repository shares nothing, so the merge would fail, and every read inside the workdir is exactly what A5 forbids.
- **Import without a recorded seed has nothing Core-owned to diff against.** The `changes` check, the merge base and the checkpoint's file list all need a base commit Core recorded itself. Today that base is never recorded: `add_worktree` receives the literal `'HEAD'` (`manager.py:366-367`), and git resolves it at add time.
- **One Core-owned store holds both ends.** The seed revision and the import commit live in the same Core-owned repository, and the import commit's parent is the seed revision. Every later git fact is then computed between two Core-recorded commits, in a repository the execution never touched. This is the one pairing that lets every row of §6 move off the workdir.

## 2. The contract

Every clause applies only when T-023's single decision says the execution is isolated (`manager.py:201`, `_workspace(..., isolated=...)`). The unisolated path is unchanged.

| # | Clause | Basis |
|---|---|---|
| C1 | **Core project store.** One Core-owned bare repository per project, created and configured only by Core, never granted to an execution and never a workdir. Candidate location `<ARCHEUS_HOME>/repos/<project_id>.git`. It holds every seed revision and import commit, each under a Core ref so neither is garbage-collected. | ADR-0053 §7.3 "Core-owned import repository"; location not decided (ADR "Not decided here") |
| C2 | **Recorded base.** Before an execution's first process, Core resolves the base to a **commit id** in the user's repository: the mission branch if it exists, else HEAD; for a detached HEAD, the commit HEAD names. Core copies that commit into the store and records it as the execution's `seed_revision` before spawn. A ref name is never recorded. | PV-20 §3.2 A1 table; ADR §7.2 |
| C3 | **Seed (trusted pre-process setup).** Core makes the execution repository in the execution's own class-7 workspace, from the seed revision in the store, before any process of that execution exists. It is a copy of that revision only: no linked worktree, alternates, shared objects or hardlinks, no user config, hooks or refs, and no uncommitted, untracked or ignored user file. The repository has no remote, and a Core-written repo-local config. | PV-20 §3.2 A5 "Seed"; §7.5 class 7 |
| C4 | **No Core git in the workspace after the first process starts.** No HEAD/branch/status read, snapshot, merge base, worktree removal or gc. A resume (same execution, `process_seq > 1`) finds the workspace exactly as left; a missing workspace refuses, and is never re-seeded or replaced. | A5; mirrors T-024's resume rule for `CLAUDE_CONFIG_DIR` |
| C5 | **Import (data only).** After Core has ended every process in the execution's Job (no live writer), Core reads the workspace's files as data, without running git in it and without honouring anything in it. It writes them into the store as a Core commit whose parent is `seed_revision`, and records that commit as `import_revision`. | A5 "Import"; §3.9 "no live writer" |
| C6 | **Canonical revision.** `import_revision` is the only revision any later Core step uses: verification's `revision`, the `changes` diff, merge-back, a continuation's seed, the progress digest and the checkpoint's file list. The execution's own HEAD, commits and refs are claims and are never read. | A5 "Core's pinned import commit is the canonical revision" |
| C7 | **Pinned configuration.** Every Core git operation in C1-C6, and every merge, diff, checkout or push over execution-derived content, runs under one Core-pinned configuration. No system, global or execution config; no hooks, fsmonitor, filters, diff/merge drivers, submodule recursion or LFS transfer. The exact pin is not decided (ADR); the §7 candidate is **UNVERIFIED**. | A5 bullet 4; owner confirmation 2026-10-07 |
| C8 | **Merge-back from the store.** The import commit reaches the mission branch in the user's repository only from the store, under C7. Every isolated task with a project merges back, whatever its recorded `workspace_mode`. | A1 "only through the A5 import and P13's merge-back"; ADR Consequences A1 |
| C9 | **Verification fail-closed.** R4b verifies a fresh Core checkout of `import_revision` under a confined verifier. Until that verifier (A6) exists, no command check runs for an isolated import, or for a mission branch holding one: those checks are missing evidence (ERROR or AWAITING_HUMAN), never PASSED. Only data-only checks may run, such as `changes` computed in the store. | PV-20 §3.9 fail-closed mode; A6 |
| C10 | **Failure is fail-closed.** If the seed fails, nothing is spawned; the existing workspace refusal applies (`manager.py:202-205`), an isolation-establishment failure. If the import fails, the execution has no canonical revision, so its task cannot pass verification or merge. The state and charge for that are an owner decision (§8 Q8). | A1 "transient … isolation-establishment failure"; C6 |

## 3. Durable authority: what is recorded, and where

New fields are proposed in the Execution row's body. Precedent: `inventory_sha256` "lives in the execution row's body: nothing queries by it, so it needs no column" (`migrations/0015_opt_ins.sql:9-10`; field at `entities.py:1010`). The API schema for Execution is `'open': True` (`schemas.py:508`), so no schema change is required.

| Fact | Today | Under the contract | Recorded in |
|---|---|---|---|
| Base of a task's work | Ref name `'HEAD'` or the mission branch, resolved by git inside `git worktree add`; never stored (`manager.py:366-367`, `local.py:373`) | Commit id resolved and copied into the store before spawn (C2) | **new** `Execution.seed_revision`, written by `prepare_process` (`executions.py:95-124`, beside `workdir`/`branch` at `:116-117`) and carried in its `execution.prepared` event (`:121-123`) |
| Where it ran | `Execution.workdir`: the per-task worktree, or the user's root (`entities.py:985`) | `ExecPaths(e.id).work` (`paths.py:149`), class 7, per execution | `Execution.workdir` (unchanged field) |
| Branch label | `Execution.branch` = the worktree's task branch, or the root's current branch (`entities.py:986`) | The task branch `archeus/<mission>.<key>` that Core names at seed. It is a Core-authored label only; it is not read back | `Execution.branch` (unchanged field). It drives merge-back through `settle_task` (`verification.py:256`) |
| Canonical revision | HEAD observed after the snapshot commit (`worker.py:174-178`; `Verification.revision`, `entities.py:1142`) | Core's import commit (C5, C6) | **new** `Execution.import_revision`. `Verification.revision` takes it unchanged |
| Base for the `changes` check | `git merge-base` in the user's root, between the workdir HEAD and the mission branch or HEAD (`worker.py:181-183`) | Computed in the store between `import_revision` and the mission head, or simply `seed_revision` (owner Q10) | `Verification.base_revision` (`entities.py:1143`), unchanged field |
| Progress digest (ADR-0047) | Git over the workdir: HEAD, binary diff, untracked hashes (`local.py:324-354`) | The tree id of `import_revision`; None when there is no import (the guard already reads None as "no progress", `executions.py:499`) | `Execution.end_state_digest` (`entities.py:1008`), unchanged field |
| Checkpoint `files_changed` | `git diff --stat HEAD` in the workdir (`local.py:315-321`) | `diff --stat seed_revision import_revision` in the store under C7 | `Checkpoint.files_changed`, unchanged |
| Merge result | `Task.merged_revision`, `Mission.integration_base/head` (`entities.py:924`, `:736-737`) | Unchanged meaning; the merged commits now arrive from the store (C8) | Unchanged |
| The store | — | Core-private state, classes 4-6, never granted | A path under `ARCHEUS_HOME`. Its refs name the execution id |

## 4. Ownership: per execution, not per task

Today the workspace belongs to the **task**. The path is `worktrees/<project>/<mission>/<task>` (`manager.py:362`), and `add_worktree` returns early when the directory exists (`local.py:361-362`). So a retry or a P12 hand-off continuation inherits the previous execution's uncommitted files in place.

PV-20 puts the workspace in class 7 (`§7.5`), and R7 makes other executions' state inaccessible. The contract therefore makes it per **execution**, and passes content between executions only through Core-recorded commits:

| Case | Today | Contract (proposed) |
|---|---|---|
| First process | Per-task worktree or the root | New `ExecPaths(e.id).work`, seeded from `seed_revision` (C2, C3) |
| Resume of the same execution (PAUSED or AWAITING_APPROVAL; `process_seq > 1`; `_resume`, `manager.py:600`) | Same directory | Same directory, untouched. No re-seed and no git (C4). Missing means refuse |
| Hand-off continuation (a new execution with `handoff_from`, prompt from the checkpoint, `manager.py:215-218`, `:299-311`) | Same per-task directory, uncommitted work included | New workspace, seeded from the **predecessor's `import_revision`**. That requires an import at ENDED_HANDOFF (§8 Q6) |
| Retry (attempt n+1 after a charged end or failed checks) | Same per-task directory and branch | New workspace. Whether it starts from the original base or from the last attempt's import is §8 Q5 |
| After the end | Removed only by merge-back (`worker.py:294-295`) | Retention of the class-7 workspace after a successful import is §8 Q1. Never removed by `git worktree remove` |

## 5. Trusted seed setup versus execution-influenced git

- **Trusted window.** It runs from the moment Core creates the empty workspace until the execution's first process starts. Core is the only writer and no execution identity holds a grant. Core may run git in the new repository during this window, and only during it. That answers T-016 Q5 *for the window*, subject to §8 Q2.
- **The content is not trusted for that reason.** When the seed revision is the mission branch (holding merged execution output) or a predecessor's import, its in-tree `.gitattributes`, `.gitmodules` and `.lfsconfig` are execution-derived. So the seed also runs under C7 and writes files without filters or attribute processing.
- **After the first process starts,** the workspace is untrusted, and the execution's git operations there are its own (PV-20 §3.2 categories 2-3). Core reads it once more, as files, at import (C5). It does so only after the Job is closed, because a descendant the execution started can outlive its main process.
- **Ordering consequence for the manager.** `_collect` computes facts at `manager.py:528`, records the end at `:549-561`, and only then releases isolation (`:554`, `:562-563`). That release reaches `teardown` (`isolation.py:815`), whose `_close_job` (`:842`) is what kills the tree (comment at `:836`). An import has to come after the Job is closed and before `record_handoff`/`record_end`, because those consume its facts and the progress guard (`executions.py:499`). So K3 must close the Job before the import, ahead of the rest of teardown.
- **The execution's own git still reads the user's global config.** The inherited environment means it reads the user's `~/.gitconfig`, including credential helpers, until T-017 Q5 decides the isolated environment. The seed's repo-local config cannot override that. This is a dependency, not something decided here.

## 6. Every Core git operation over an execution workdir or execution-derived content today, and its replacement

Rows 1-3 run in the user's repository to make the workspace. Rows 4-15 run **inside the execution's workdir**, which A5 forbids. Rows 16-25 run over execution-derived content in the user's repository or Core's mission worktree, which A5 requires to be pinned.

| # | Operation (0c535e7) | What it does today | Replacement under the contract |
|---|---|---|---|
| 1 | `manager.py:356` `git_branch(root)` (`local.py:284`) | Decides worktree versus root | Not used for isolated executions. C2 resolves the base commit under C7 |
| 2 | `manager.py:366` `branch_exists(root, mission)` (`local.py:452`, via `git_resolve` `:402`) | Chooses the base ref | C2, under C7 |
| 3 | `manager.py:367` `add_worktree` (`local.py:357-379`: `branch_exists` `:368`, `git_is_ancestor` `:369`, `git worktree add` `:373`) | Linked worktree of the user's repository | C3 seed from the store. Never used for isolated executions |
| 4 | `manager.py:460` `git_branch(workdir)` on every hook request | Feeds `branch_ok` (`:467`) and the canonicaliser's `branch` | Nothing is read. `ctx['branch'] = e.branch`, the Core-recorded label; `branch_ok` is not evaluated from the workdir (§8 Q7) |
| 5 | `manager.py:462` `git_remotes(workdir)` (`local.py:292`) | The canonicaliser's push hosts | `{}`. The seed has no remote and the execution holds no push credential (§8 Q7) |
| 6 | `manager.py:568` `diff_stat(workdir)` (`local.py:315-321`) | Checkpoint `files_changed` | `diff --stat seed_revision import_revision` in the store, C7 |
| 7 | `manager.py:571` `end_state(workdir)` (`local.py:324-354`: `rev-parse`, `diff --binary`, `ls-files --others`, `hash-object`) | ADR-0047 progress digest | Tree id of `import_revision`; None without an import |
| 8 | `worker.py:174` `git_head(workspace)` (`local.py:394`) | The revision to verify | `e.import_revision` from the row |
| 9 | `worker.py:177` `git_dirty(workspace)` (`local.py:407`) | Whether a snapshot is needed | None. The import already captured the working tree |
| 10 | `worker.py:178` `git_snapshot` (`local.py:415-427`: `add -A`, `commit --no-verify` in the workdir) | Core's snapshot commit | None. "Core's snapshot is that import commit" (A5) |
| 11 | `worker.py:214` `run_commands(ws)` → `evidence.py:77` `node.run_check(workspace)` (`local.py:490`) | Runs the project's tests and builds in the workdir as the user | C9: none until A6. Then a confined verifier on a fresh Core checkout of `import_revision` |
| 12 | `worker.py:216` `git_head(ws)` after the checks | Detects a moving workspace | None. The import commit is immutable and the checkout is Core's |
| 13 | `worker.py:217` `git_dirty(ws, tracked_only=True)` | Same | None |
| 14 | `worker.py:249` retry `_run_and_record(..., v.workspace, ...)` | Rows 11-13 again, on the recorded workspace | As rows 11-13; `v.workspace` names no live workdir for isolated executions |
| 15 | `worker.py:295` `remove_worktree(root, e.workdir)` (`local.py:381-390`) | Deferred P11 removal after merge | Not applicable: the workspace is not a worktree of the user's repository. Retention per §8 Q1 |
| 16 | `worker.py:181` `branch_exists(root, mb)` and `:182` `git_merge_base(root, head, against)` (`local.py:429`) | Base for the `changes` check | In the store under C7, between `import_revision` and the mission head (or `seed_revision`, §8 Q10) |
| 17 | `worker.py:213` `changes_check` → `evidence.py:100` `git_numstat(root, base, revision)` (`local.py:439`) | "Did a code change change anything" | In the store under C7. This data-only check may run before A6 |
| 18 | `worker.py:282` `git_merge_base(root, revision, 'HEAD')` | Mission integration base, first merge | Under C7, after the import commit reaches the user's repository (C8) |
| 19 | `worker.py:283` `mission_worktree` (`local.py:456-469`) | Core's linked worktree on the mission branch | Under C7 (M1) or replaced (M2), §7 |
| 20 | `worker.py:285` `git_head(wt)`, `:286` `git_is_ancestor(root, revision, head)` | Already merged before a restart? | Under C7 |
| 21 | `worker.py:289` `git_merge(wt, revision)` (`local.py:471-488`: `merge --no-ff`, `diff --name-only --diff-filter=U`, `merge --abort`) | Merge-back | C8: the import commit arrives from the store, and the merge runs under C7 (M1) or in the store (M2) |
| 22 | `worker.py:256` `run_commands(v.workspace)`, `:258` `git_head(v.workspace)` (mission retry) | Mission checks on the mission worktree | C9 once the branch holds an isolated import. `git_head` under C7 |
| 23 | `worker.py:317`, `:350` `git_head(ws)` on the mission worktree | Stale-head detection | Under C7 |
| 24 | `worker.py:347` `run_commands(ws)` for mission criteria | Runs merged output as the user | C9 |
| 25 | `worker.py:363` `git_numstat(root, base, head)` | Diff given to the mission review | Under C7 |

Checked and found not to be workdir operations:
- There is **no Core push** at `0c535e7`; a search of `archeus/` finds none. C7 must cover push when one is added (A5).
- `inspection.py:94` and `:258` run git on registered project roots: the user's repository at registration time, not execution-derived. They are outside this card.
- The hook (`archeus/harnesses/hook.py`) runs no git.
- `checkpoint.derive` and `pressure.progressed` only consume `_facts` (rows 6-7).
- `worker.py:323` uses the user's project root as a mission workspace when nothing was integrated. That is unisolated behaviour and outside this card, but under A1 it must not apply to a mission that integrates an isolated import (C8, C9).

## 7. The minimal candidate, and its alternatives

**Candidate M (proposed).** Every mechanic below is **UNVERIFIED**.

- **Store (C1).** A bare repository created by Core with an empty template, refs `refs/archeus/exec/<execution_id>/seed` and `.../import`.
- **Base (C2).** Resolve the ref to a commit id in the user's repository under C7, copy that commit's objects into the store (candidate: a fetch run in the store, checked against the recorded id), then record `seed_revision`.
- **Seed (C3), form S-a.** Core writes the seed revision's tree into the empty workspace as files, read as objects from the store without filters or attributes. Candidate: `ls-tree -r -z` plus `cat-file --batch`. Core then initialises the execution repository with an empty template, writes those objects into it, and makes one Core commit of the same tree on the task branch, with a Core-written repo-local config, no remote and an index built by Core.
  - The execution-side commit is a new root commit whose tree equals the seed revision's tree; its id differs from `seed_revision`.
  - `seed_revision` stays Core's record. The import's parent is `seed_revision`, never the execution-side commit.
- **Import (C5).**
  - Core walks the workspace as data without following links (§8 Q3). It skips the root `.git`, and nested `.git` directories as §8 Q3 decides.
  - It writes each file into the store as a blob without filters. Candidate: `hash-object -w --no-filters`.
  - It builds the tree with a Core temporary index (candidate: `GIT_INDEX_FILE`, `update-index --index-info`, `write-tree`) and commits it with `commit-tree -p <seed_revision>` under Core's identity (`local.py:31`).
  - Nothing in the workspace is executed or honoured, and git never runs with the workspace as its directory.
- **Pin (C7), candidate.**
  - An environment that excludes system and global config: candidate `GIT_CONFIG_NOSYSTEM=1`, and `GIT_CONFIG_GLOBAL` pointing at an empty Core file.
  - `-c` overrides: `core.hooksPath` pointing at an empty Core directory, `core.fsmonitor=false`, `protocol.allow=never` plus `protocol.file.allow=always` for store transfers, and `submodule.recurse=false`.
  - No filter or driver defined.
  - For operations that read in-tree attributes (merge, checkout), an empty attribute source. Candidate: `--attr-source`/`GIT_ATTR_SOURCE` set to the empty tree. That needs a recent git and is **UNVERIFIED**.
  - Today no pin exists: `proc.git` passes nothing (`proc.py:76-81`), and only identity flags exist (`local.py:416`, `:476`).
- **Merge-back (C8), form M1.** Copy the import commit from the store into the user's repository under C7, then merge it in the existing mission worktree under C7. P13's mission branch and mission worktree stay where they are.
  - The user's **own** repo-local config is still read by that merge. Whether C7 neutralises it enough (merge drivers named by execution-derived attributes, the user's hooks) is §8 Q9.
- **Verification (C9).** `changes` runs in the store. Command checks are not run for isolated imports until A6.

| Alternative | Differs in | Why not the candidate |
|---|---|---|
| S-b: shallow clone of the store (`--depth 1`, `--no-local`, `--no-hardlinks`, empty template), then checkout under C7 | The execution's HEAD id equals `seed_revision` | The checkout reads in-tree attributes and filters inside the workspace; the shallow graft is extra state. Kept as §8 Q2 |
| S-c: files only, no `.git` | Core runs no git in the workspace at all | PV-20 §3.2 names "a separate execution repository", and the execution's category 2-3 git operations need one. Owner only |
| Import with `git add -A` and a work tree pointed at the copy | Simpler to write | Honours the execution's `.gitattributes`, clean filters and ignore rules during a Core operation. Rejected under C7 |
| M2: merge in the store (`merge-tree --write-tree`), then publish the result to the user's mission branch as a ref update under C7 | The user's repo config is never read by the merge | Larger change to P13 (the mission branch's home and mission verification's checkout). §8 Q9 |
| G-1 (Core git in the execution repository, hardened), G-2 (bundle produced inside), G-3 (Core parses git objects itself), R4a-A (linked worktree plus ACL split) | — | Not chosen by ADR-0053 (Alternatives). Listed only to say they are out |

## 8. Material owner decisions this contract does not make

Collected again as numbered questions in §10.
- **Retention and location** of the store and of class-7 workspaces after import (ADR "Not decided here"; T-016 Q3, Q10).
- **Seed form**, S-a or S-b: which one is "a copy of the base revision only" (A5), and whether the execution-side HEAD must equal the recorded id.
- **Links** in both directions: symlinks, junctions and other reparse points, hardlinks, nested `.git` directories, gitlinks and submodules, in the seed tree (modes 120000 and 160000) and in the imported working tree. Never follow, skip with a record, or refuse the import (ADR "Not decided here": link and reparse-point handling). Following a junction at import would pull files from outside the workspace into the mission branch.
- **Import scope**: everything, or a Core-parsed ignore list (from the execution's tree, or from the seed's), and size bounds.
- **Retry start**: the original base, or the last attempt's import.
- **Hand-off continuation**: seeded from the predecessor's import. This changes P12's "continue the same directory" to "continue from Core's record of it".
- **Hook checks**: what replaces `branch_ok` and the canonicaliser's `branch`/`remotes` once Core may not read the workdir (T-016 Q6).
- **Import failure**: the execution and task state and charge when C5 cannot complete.
- **Merge-back form**, M1 or M2, and how the user's own repo config is kept out of a merge of execution-derived content.
- **Base of the `changes` check**: the merge base computed in the store, or `seed_revision`.
- **Verification interim**: C9 means every isolated code task needs a human until A6 exists. Is that acceptable as the path to activation, or does activation wait for A6?

## 9. Implementation cards (proposed), files, fake tests, dependencies

All tests use owned temporary data only: repositories the test creates in `tmp_path`, planted sentinel files and fake nodes. No user repository, no native isolation, no real CLI. Real git in temporary repositories, as `tests/v1/integration/test_verification.py` already does.

| Card | Change | Files | Fake tests (owned temp data) | Depends on |
|---|---|---|---|---|
| K1 · Store and pinned runner | C1, C7: a pinned git runner and the store's create/transfer | `archeus/node/local.py`, `archeus/infra/paths.py` (store path), new `tests/v1/integration/test_repo_store.py` | Store is bare with no hooks and an empty template. A hook, an fsmonitor command and a filter planted in a temp "user" repo, and in a temp global config under a fake HOME, leave a sentinel uncreated during transfer. The pinned runner ignores a planted global `core.hooksPath` | Owner Q1 (location), Q9 (pin scope) |
| K2 · Recorded base and seed | C2, C3: `seed_revision` field and record; seed into `ExecPaths.work` | `archeus/core/domain/entities.py` (`seed_revision`, `import_revision`, 40-hex check like `:1014-1015`), `archeus/core/application/executions.py` (`prepare_process`), `archeus/node/local.py` (seed), tests in `test_repo_store.py` and `tests/v1/unit/test_execution_units.py` | The seed holds exactly the recorded tree. Its own `.git`: no alternates, no `commondir`/`gitdir` file, no hooks, no remote. No seeded file has `st_nlink > 1` (Python on NTFS **UNVERIFIED**). Uncommitted, untracked and ignored user files are absent. Mission branch versus HEAD versus detached HEAD each record the right id. Hostile `.gitattributes` in the base leave a filter sentinel uncreated. The resume rig asserts no re-seed and refusal when the workspace is missing | K1; owner Q2, Q3 (seed half) |
| K3 · Import | C5: close the Job, import, record `import_revision` before `record_end`/`record_handoff`; continuation seeded from the predecessor's import | `archeus/node/local.py` (import), `archeus/core/execution/manager.py` (`_collect` ordering, `_facts`), `archeus/node/isolation.py` (only if the Job close must be split from the rest of teardown), `archeus/core/application/executions.py` (record), tests | **A5 hostile repository**: `.git/config` with `core.fsmonitor` and a filter driver, `.git/hooks/*`, `.gitattributes`, `.gitmodules`, `.lfsconfig` and `refs/replace/` in the workspace. The import leaves the sentinel uncreated, and the import tree's bytes equal the files written. Each link decision (Q3) is pinned by a test. A writer still alive in a fake Job means no import until it is closed | K2; owner Q3, Q4, Q6, Q8 |
| K4 · Git facts from Core records | Rows 4-7: hook context, `files_changed`, `end_state` for isolated executions | `archeus/core/execution/manager.py`, `tests/v1/unit/test_execution_units.py` | A fake node whose workdir git methods raise is never called on the isolated path, and a hook request is still answered. The progress digest equals the import tree id. The checkpoint stat comes from the store | K3; owner Q7 |
| K5 · Verification and merge-back from the import | Rows 8-25: `revision`/`base` from records, `changes` in the store, C9 fail-closed, C8 merge | `archeus/core/verification/worker.py`, `archeus/core/verification/evidence.py`, `archeus/core/application/verification.py` (only if C9 needs an explicit missing-evidence path), `archeus/node/local.py` (merge transfer), tests in `tests/v1/integration/test_verification.py` style | Verification uses `import_revision`, and no git runs in the workdir (fake node raises). No command check runs for an isolated import, and none is PASSED. The merge brings the import into a temp "user" repository's mission branch, and a planted merge driver and hook leave the sentinel uncreated. An in-place-recorded isolated task still merges back | K3; owner Q9, Q10, Q11 |
| K6 · Lift T-027 for git roots | `_workspace` seeds instead of refusing, for a git first root only | `archeus/core/execution/manager.py`, `tests/v1/unit/test_execution_units.py` | The T-027 trace rows become "seed, no root probe beyond C2". Non-git roots are still refused. The unisolated controls are unchanged | **All of K1-K5 accepted and the owner's explicit go.** Also T-016 W5 (refusal before dispatch for a non-git root), W1 (workspace shape check) and W7 (migration) before production; S2-G (T-004) and T-008 evidence before any real isolated run |

Serialisation:
- K2, K3, K4 and K6 share `manager.py`, `executions.py` or `test_execution_units.py`, so they go one at a time.
- K1 and the store half of K5 can be prepared in parallel with K2.
- T-029 (on `base.py`) does not overlap any card here.

## 10. Owner questions

1. Where do the Core project store and an imported execution's class-7 workspace live, and how long is each kept (store GC, workspace deletion after a successful import)?
2. Seed form: S-a (a new execution-side commit holding the base tree, with `seed_revision` kept as Core's record) or S-b (a shallow clone whose HEAD id equals `seed_revision`)? Which one is "a copy of the base revision only"?
3. Links, in the seed and at import: symlinks, junctions and other reparse points, hardlinks, nested `.git`, gitlinks and submodules. Never follow and skip with a record, or refuse the whole import?
4. Import scope: the whole working tree, or a Core-parsed ignore list (from the execution's tree or from the seed), and what size bound?
5. A retry (attempt n+1): seeded from the original base, or from the last attempt's import?
6. A hand-off continuation: seeded from the predecessor's `import_revision` (an import at every ENDED_HANDOFF)? This replaces today's shared per-task directory.
7. Once Core may not read the workdir, what replaces `branch_ok` and the canonicaliser's `branch`/`remotes`: the Core-recorded label and `{}`, or something else?
8. If the import fails: what execution and task state, and is it charged?
9. Merge-back: M1 (import into the user's repository, merge in the mission worktree under the pin) or M2 (merge in the store, publish by ref update)? And how must the user's own repo config (hooks, merge drivers) be kept out of a merge of execution-derived content?
10. The base of the `changes` check: the merge base computed in the store, or `seed_revision`?
11. Until A6 exists, is it acceptable that every isolated code task's command checks are missing evidence, so it needs a human? Or does activation wait for A6?
12. Should the cards be authorized as K1-K5 behind T-027's refusal, with K6 as a separate owner go? Or should none start until questions 1-11 are answered?
