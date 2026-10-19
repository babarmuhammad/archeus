# T-016 · A1 private workspace: implementation slices and migration contract

Prepared by Claude, 2026-10-12. Planning only: no code, no test run, no OS call, no design ruling.

Sources, all read at worktree `D:\archeus-pv20-s2-l`, branch `pv20-s2`, HEAD `3489a39`:
- `docs/architecture/pv20-execution-isolation-design.md`: §3.2 (A1/A5 text), §3.4, §3.7 (last bullet, migration), §6 items 19, 20 and the R2/R7 notes, §7.5, §8 (A1 and A5 acceptance bullets).
- `docs/architecture/decisions/ADR-0053.md`: §7 items 2 and 3 (A1-1, G-4), Consequences (A1 and A5 bullets), "Not decided here".
- `archeus/core/execution/manager.py`, `archeus/node/local.py`, `archeus/node/isolation.py`, `archeus/infra/paths.py`, `archeus/harnesses/base.py`, `archeus/core/verification/worker.py`, `archeus/core/application/work.py`, `archeus/core/engine.py`, `archeus/core/planning/planner.py`, `archeus/core/domain/entities.py`, `archeus/core/world/inspection.py`, `claude_sessions/repos.py`, `claude_sessions/proc.py`.
- `D:\Claude\docs\project-context\pv20-a2-a3-s2-addendum-2026-10-11.md`, "S2 contract constraints".

Everything below about what a slice would do is a proposal. "Required" means the canonical text cited beside it says so.

## 1. Current behaviour: unisolated executions (as built)

How `ExecutionManager._workspace` (manager.py:324-350) chooses a workdir today. It runs inside `_spawn` (manager.py:187-192) and its answer is recorded by `prepare_process` (manager.py:236-238) before any process exists.

| Case | What Core does today | Where |
|---|---|---|
| No project | `ExecPaths(e.id).work` = `run/exec/<id>/own/work`, created by the manager, branch None | manager.py:326-331; paths.py:149; pinned by `test_a_project_less_workspace_is_the_executions_own_never_its_core_directory` (test_execution_units.py:676) |
| Project with no root | `OSError`, then `X.refuse(stop_reason='workspace')`, which is charged and so spends the task's attempts | manager.py:335-336, 189-192; `test_a_workspace_that_cannot_be_made_spends_the_tasks_attempts` (test_verification.py:457) |
| Git first root, task `workspace_mode == 'worktree'`, HEAD on a branch | Linked worktree: `git worktree add -b archeus/<mission>.<task> <ARCHEUS_HOME>/worktrees/<project>/<mission>/<task> <base>`. `<base>` is the mission branch if it exists, else the literal `'HEAD'`: a ref name resolved by git at add time, and never recorded as a commit | manager.py:339-349; local.py:358-380 |
| Same, a retry or a P12 hand-off continuation of the same task | Reuses the existing per-task directory (`add_worktree` returns early when it already exists), so a later execution inherits the earlier one's uncommitted work | manager.py:344; local.py:362-363 |
| Git first root, detached HEAD | `git_branch` returns None, so even a `worktree` task falls through to running in the **user's project root** | local.py:285-290; manager.py:339, 350 |
| `workspace_mode == 'in_place'` (the planner's default for every kind except `code_change`) | The **user's project root**, branch = its current branch | planner.py:279-280; manager.py:350 |
| First root not a git repository | The **user's project root**, branch None. Project registration requires a repository *at or under* some root (inspection.py:121), not that the first root is one | manager.py:338, 350 |
| Scheduling | An `in_place` task conflicts with every other task of its project, so the two never run together | engine.py:80-86 |

Git operations Core runs under the user's identity today, against the execution's workdir or against the user's repository:

| Operation | Against | Where |
|---|---|---|
| `git_branch`, `branch_exists`, `add_worktree` | the user's repository (root) | manager.py:338, 348-349 |
| `git_branch`, `git_remotes` on **every hook request**, feeding `branch_ok` and the canonicaliser's context | the workdir | manager.py:439-444 |
| `diff_stat`, `end_state` at the end (checkpoint, ADR-0047 progress guard) | the workdir | manager.py:539-545; local.py:316-354 |
| `git_head`, `git_dirty`, `git_snapshot` (`add -A` + `commit --no-verify`), `git_merge_base` before verification | the workdir, then root | worker.py:169-184 |
| `git_head`, `git_dirty` after the checks | the workdir | worker.py:216-217 |
| merge-back: `git_merge(<mission worktree>, revision)`, then `remove_worktree` | Core's mission worktree, itself a linked worktree of the user's repository (`_mission_wt`, worker.py:47-48) | worker.py:283-295 |

The merge resolves `revision` only because a linked worktree shares the user's object store. This is relevant to sequencing below (§4, W3/W6).

## 2. Current behaviour: an isolated execution (S1 + S2-L, as built)

- **Who runs isolated.** `Isolation.requested` (isolation.py:552-563) says yes only for an execution that already has a record, or one an `authorize` callback approves. While `PRODUCTION_DISPATCH_ENABLED` is False, only a test harness gets that yes. `LocalNode` builds its `Isolation` with no `authorize` (local.py:45), so no production execution is isolated.
- **The workspace is chosen before isolation is decided.** `_workspace` runs at manager.py:188. The isolation decision happens inside `node.spawn` at manager.py:255 (local.py:59-62). An isolated test-harness execution therefore gets whatever the unisolated rule chose, including the user's project root in the `in_place`, detached-HEAD and non-git cases.
- **The plan names that workdir as the workspace.** `default_plan` plans `Grant(spec.workdir, 'rw', 'workspace')` (isolation.py:1133). It is planned only: no ACL writer exists (T-011 F1).
- **The invariant does not judge the workspace's shape.**
  - Condition 2 asks only that the workspace is a non-empty path to an existing directory (isolation.py:209, 217).
  - Condition 5 keeps it apart from classes 1-3 (isolation.py:248), and `test_a_workspace_that_is_cores_own_directory_fails_closed` (test_pv20_isolation.py:464) covers Core's own directory.
  - Nothing checks that the workspace is not the user's project root, not a linked worktree, and not a repository with alternates.
- **Why it still fails closed today.** The production plan fails condition 2 because nothing supplies `broker` and the runtime and hook rows are not granted (default_plan docstring, isolation.py:1117-1124). The workspace check plays no part in that.

## 3. Required isolated behaviour (A1, A5) against what exists

| Requirement (cited) | Current isolated behaviour (§2) | Slice |
|---|---|---|
| Every isolated execution works in a Core-established workspace distinct from the user's project root, the user's `.git` and classes 1-6 (PV-20 §3.2 A1; ADR-0053 §7.2) | Same choice as unisolated; the project root is possible | W0, W1, W2 |
| Git first root: a separate execution repository seeded from the recorded base revision (mission branch if it exists, otherwise HEAD); detached HEAD: from the recorded commit (§3.2 table) | Linked worktree, or the root; the base is never recorded as a commit | W3 |
| No project: an empty execution-private workspace in class 7, never the bare `run/exec/<id>/` (§3.2 table) | **Already built** (S2-L): `own/work`, test-pinned | — (W1 adds the invariant side) |
| Non-git first root: structurally refused **before dispatch**, never entering a spawn/retry loop (§3.2; ADR-0053 §7.2) | Runs in the root | W5 (W2 is the interim fail-closed) |
| `in_place` withdrawn for isolated executions (§3.2; §6 item 19) | Honoured | W2 |
| Seed is a copy of the base revision only: no linked worktree, shared objects, alternates, hardlinks, or anything exposing the user's `.git` (§3.2 A5 "Seed"; §6 item 20) | Linked worktree | W3, with W1 as the guard |
| Core never runs git, or anything reading git configuration, against an execution repository under the user's identity (§3.2 A5; ADR-0053 Consequences, A5 bullet, which lists `git_head`, `git_dirty`, `git_snapshot`, `git_merge_base`, the per-request HEAD/branch read and `git worktree add`) | Every row of §1's second table that targets the workdir | W4, W6 |
| Working tree imported as data into a Core-owned import repository; the pinned import commit is the canonical revision; Core-pinned configuration for every Core git operation over execution-derived content (§3.2 A5 "Import", "Core-pinned configuration") | Absent: no import repository, no pinned configuration (`proc.git` passes no `-c` pinning, proc.py:76-81; only identity flags exist, local.py:419, 476) | W6 |
| Workspace and `CLAUDE_CONFIG_DIR` are class 7 (§7.5; §6 R2) | `own/work` is class 7; project workspaces live under `<ARCHEUS_HOME>/worktrees/` | W3 (location is an open question, §7 Q3) |
| Existing worktrees and `in_place` tasks migrate; neither falls back to the user's root (§3.7 last bullet). Activation without a compatibility shim needs verified absence of live executions using the old layout (addendum) | Not addressed | W7 |

## 4. Slices

Rules every slice follows: the unisolated path stays byte-for-byte as it is (each change is keyed on "this execution is isolated"); no ACL writer; no switch flipped (`PRODUCTION_DISPATCH_ENABLED`, `A4_ENFORCED`, `CAPABILITIES` unchanged); no Windows isolation API. "Fake tests" means fake boundaries. Real git in `tmp_path` repositories is used the way `tests/v1/integration/test_verification.py` already does. No slice makes a workspace *usable* inside an AppContainer: that needs grants, which are S2-G's (T-004, blocked).

### W0 · The isolation decision reaches workspace selection
- **Why**: §2, second bullet. A1 cannot be applied by a function that does not know the execution is isolated.
- **Change**: `_spawn` asks once whether this execution runs isolated, the same way `_isolation_record` reaches the node (`getattr`, manager.py:701-707, so a node with no isolation authority answers "no"). It passes the answer to `_workspace` and to `node.spawn(..., isolated=...)`; that parameter already exists (local.py:49, 59).
- **Files**: `archeus/core/execution/manager.py`; `tests/v1/unit/test_execution_units.py`.
- **Fake tests**:
  - `test_the_isolation_decision_is_taken_once_and_passed_to_spawn`: a fake node counts `requested` calls and records the `isolated=` it was given.
  - `test_an_unisolated_spawn_is_unchanged`: same argv/workdir/branch as before for each §1 case.
- **Overlap**: manager.py and test_execution_units.py are in T-015's candidate scope.

### W1 · The invariant judges the workspace's shape
- **Change**: in `check_invariant`, condition 2 also fails when the workspace is any of:
  - a linked worktree or submodule: `repos.classify(workspace)` is `'worktree'` or `'submodule'`, or its `.git` is a file;
  - a repository with `.git/objects/info/alternates`;
  - at or inside any path the request names as forbidden (the project's roots). That last check needs one new `IsolationRequest` field, filled by `default_plan` from the spec.
- **Files**: `archeus/node/isolation.py`; `tests/v1/unit/test_pv20_isolation.py`.
- **Fake tests** (each expects `unmet_conditions == ('grants',)`):
  - `test_a_linked_worktree_workspace_fails_closed`: `.git` is a file whose gitdir points into `.git/worktrees/`.
  - `test_a_workspace_with_alternates_fails_closed`.
  - `test_a_workspace_at_or_inside_a_project_root_fails_closed`: parametrized "is root" / "inside root".
  - `test_a_separate_repository_workspace_passes`.
- **Reuse**: `repos.classify` (repos.py:78-93), `_within` / `_norm` (isolation.py).
- **Not covered**: hardlinks. A per-file `st_nlink` walk is a seed-time assertion (W3), not an invariant check.
- **Overlap**: none with T-015. Independent of every other slice.

### W2 · No isolated `in_place`, no isolated project root (interim fail-closed)
- **Change**: for an isolated execution, `_workspace` ignores `workspace_mode` and never returns the project root. Until W3 exists there is no Core-established project workspace, so an isolated execution with a project raises `OSError`. The existing refusal then applies (`stop_reason='workspace'`, charged, bounded by `max_attempts`).
- **This is not A1's "before dispatch"**: the charged refusal still runs a bounded spawn/retry. W5 is the conforming refusal.
- **Files**: manager.py; test_execution_units.py.
- **Fake tests**:
  - `test_an_isolated_in_place_task_never_runs_in_the_project_root`;
  - `test_an_isolated_detached_head_task_never_runs_in_the_project_root`;
  - `test_an_isolated_non_git_root_never_runs_in_the_project_root`;
  - `test_an_isolated_project_less_execution_keeps_own_work`;
  - unisolated tests unchanged.
- **Depends on**: W0. **Overlap**: T-015's files.

### W3 · Recorded base and copy seed (separate execution repository)
- **Change**:
  - Resolve the base to a commit in the user's repository: mission branch if `branch_exists`, else HEAD; for a detached HEAD, the commit HEAD names.
  - Record it before spawn.
  - Create a fresh repository holding that revision's tree as the isolated workspace.
- **Candidate seed mechanics, not chosen** (ADR-0053 leaves them open):
  - (a) `git archive <sha>` from the user's repository, extract, then `git init` plus one Core commit under pinned configuration;
  - (b) a `--no-local --no-hardlinks` clone of that one revision.
  - Either must produce: no linked worktree, no alternates, no hardlinks, no user hooks/config, no user refs beyond the seed, and none of the user's uncommitted, untracked or ignored files.
  - That (b) avoids hardlinks and shared objects on Windows is documented git behaviour, **not verified here**.
- **Files**:
  - `archeus/node/local.py`: a seed method beside `add_worktree`;
  - manager.py `_workspace`;
  - wherever the base is recorded (§7 Q4): an `Execution` field means `entities.py` + `archeus/api/schemas.py`, and if it is written by `prepare_process`, `archeus/core/application/executions.py`;
  - tests in a `test_verification.py`-style integration file.
- **Fake tests** (real git, tmp repositories):
  - `test_the_seed_has_its_own_git_dir_and_no_alternates`;
  - `test_no_seeded_file_is_a_hardlink` (`st_nlink == 1` for every file; Python's `st_nlink` on NTFS is **not verified here**);
  - `test_the_seed_is_exactly_the_recorded_revision_tree`;
  - `test_a_hook_and_a_config_key_planted_in_the_user_repo_are_absent_from_the_seed`;
  - `test_uncommitted_untracked_and_ignored_files_are_not_seeded`;
  - `test_the_mission_branch_is_the_base_once_it_exists`;
  - `test_a_detached_head_seeds_from_the_recorded_commit`.
- **Reuse**: `git_resolve` (local.py:403), `branch_exists` (local.py:453), `mission_branch` (manager.py:46), `ExecPaths.work` if the location is class 7 (§7 Q3), `proc.run` / `proc.git`.
- **Depends on**: W0, W2; must be **enabled together with W6** (§5). **Overlap**: manager.py; executions.py if the base is recorded through `prepare_process`; T-017 if the location is `own/` (class 7, which T-017 also plans).

### W4 · Core stops running git in an isolated execution's workdir (live and end-of-run reads)
- **Change**: for an isolated execution, remove:
  - the per-request `git_branch` / `git_remotes` (manager.py:439-444);
  - the end-of-run `diff_stat` / `end_state` (manager.py:539-545).
- **Replacements are open** (§7 Q6, Q7): for `branch_ok` and the canonicaliser's `branch` / `remotes`, and for the ADR-0047 progress digest.
- **Files**: manager.py; test_execution_units.py.
- **Fake tests**:
  - `test_no_git_runs_in_an_isolated_workdir_while_it_runs`: a fake node whose git methods raise on that path; a hook request is still answered.
  - `test_no_git_runs_in_an_isolated_workdir_at_its_end`.
- **Depends on**: W0. **Overlap**: T-015's files.

### W5 · Structural refusal before dispatch
- **Change**: in `Work.dispatch_task` (work.py:315), before `new_execution`, a project whose first root is not a git repository (`repos.classify(root) is None`) is refused. No Execution row, no spawn, no retry, when the dispatch will be isolated.
- **What "will be isolated" means at dispatch is open** (§7 Q1). Today that fact exists only per execution, at spawn. A candidate trigger is `production_dispatch_enabled()`, which leaves today's behaviour unchanged because it is False.
- **The resulting Task state and `failure_class` are P8's and P11's** (ADR-0053 "Not decided here"; §7 Q2).
- **Files**: `archeus/core/application/work.py`; `entities.py` if a new failure class is added; a test in the dispatch/planning tests (not T-015's `test_execution.py`, to avoid the overlap).
- **Fake tests**:
  - `test_a_non_git_first_root_is_refused_before_any_execution_exists` (zero Execution rows, zero spawn attempts; matches the PV-20 §8 A1 bullet);
  - `test_an_unisolated_non_git_project_still_dispatches`.
- **Overlap**: none with T-015 if the test lives outside its files.

### W6 · Import as data (A5): separate card, larger than the rest
- **Change**:
  - A Core-owned import repository.
  - Copy the execution's working tree, without `.git`, as data. Link and reparse-point handling are implementation details (ADR-0053 "Not decided here").
  - Make the import commit under a Core-pinned configuration; it becomes the canonical revision, recorded in Core state.
  - The verification worker's `_workspace_of`, `_run_and_record` and `_merge` (worker.py:169-184, 210-217, 269-301) use the import commit and never the workdir's git.
  - Merge-back takes the revision from the import repository, not from a shared object store.
- **Files**: `archeus/node/local.py`; `archeus/core/verification/worker.py`; whatever records the import commit; a new integration test file.
- **Acceptance**: the PV-20 §8 A5 bullet. A hostile execution repository (config, hooks, attributes, sub-repository and large-file configuration, replaced refs) leaves a planted sentinel uncreated through seeding, import, git facts, merge, checkout and push, and the recorded revision is Core's import commit.
- **Not in scope**: verification still runs as the user. R4b/A6 is its own remediation (ADR-0053 Consequences, first bullet).
- **Depends on**: W3. **Overlap**: none with T-015's listed files, unless the import commit is recorded through `executions.py`.

### W7 · Migration (PV-20 §3.7 last bullet)
- **Contract to implement, once isolated dispatch is production (E)**:
  - An execution that began unisolated never resumes isolated in its old workdir. `requested()` can authorize an unrecorded execution at resume (isolation.py:557-563), and `_workspace` would then hand back the old linked worktree. W1's check makes that fail closed at the invariant; W7 makes the manager refuse it before planning a grant.
  - Tasks recorded `in_place` are served by W2/W3 when dispatched isolated.
  - No compatibility shim, and activation only after a verified absence of live executions using the old layout (addendum). That verification is evidence, not code, and authorizes no termination.
- **Files**: manager.py (resume path); possibly the boot reconcile in manager.py; tests in T-015's files.
- **Disposition of existing `<ARCHEUS_HOME>/worktrees/` content and its uncommitted work is an owner question** (§7 Q9). `remove_worktree` (local.py:382) is the existing removal if one is decided.
- **Depends on**: W0-W3, W6, and E. **Overlap**: T-015's files.

**No slice proposed** for the scheduler's `in_place` serialisation (engine.py:80-86) or the planner's `in_place` default (planner.py:279-280). ADR-0053's A1 consequence says these rules "no longer apply" to isolated executions. Leaving them in place only serialises more than needed, and it is not a security question. Whether the planner should stop emitting `in_place` once E is on is §7 Q9.

## 5. Dependencies and file overlap

| Slice | Files | Depends on | Overlaps T-015 (executions.py, manager.py, test_execution_units.py, test_execution.py) | Other |
|---|---|---|---|---|
| W0 | manager.py, test_execution_units.py | — | **yes** | — |
| W1 | isolation.py, test_pv20_isolation.py | — | no | none |
| W2 | manager.py, test_execution_units.py | W0 | **yes** | — |
| W3 | local.py, manager.py, base record site (entities.py, api/schemas.py, maybe executions.py), integration test | W0, W2; enable with W6 | **yes** | T-017 if class-7 `own/` location |
| W4 | manager.py, test_execution_units.py | W0 | **yes** | — |
| W5 | work.py, (entities.py), dispatch test | Q1, Q2 answered | no | — |
| W6 | local.py, worker.py, record site, new test | W3 | only if recorded via executions.py | R4b/A6 separate |
| W7 | manager.py, tests | W0-W3, W6, E | **yes** | addendum activation rule |

- **Sequencing constraint.** W3 alone would break isolated verification and merge-back. The seeded repository's commits are not in the user's object store, and worker.py:178-189 and 283-289 run git in the workdir and merge a revision the mission worktree cannot resolve. So W3 is either enabled together with W6, or isolated project executions stay refused (W2) until both land.
- **T-015 coordination.** W0, W2, W3, W4 and W7 edit manager.py; T-015 must finalize its file claim first, or the two serialize. W1 and W5 can proceed in parallel with T-015.
- **Outside every slice.** Making the workspace reachable by the AppContainer is S2-G (T-004). Windows evidence for any of it is T-008 / W-1 territory, not this card's.

## 6. Reuse

| Need | Existing code |
|---|---|
| Resolve a base to a commit | `LocalNode.git_resolve` (local.py:403), `branch_exists` (local.py:453), `mission_branch` (manager.py:46) |
| Classify a directory as repo / worktree / submodule / none, without git | `claude_sessions.repos.classify` (repos.py:78-93), already used by `inspection.discover` |
| Run git with pinned decoding, no console | `proc.run` / `proc.git` (proc.py:47-81) |
| Core commit identity | `CORE_GIT_NAME` / `CORE_GIT_EMAIL` and the `-c` identity list (local.py:31, 419) |
| A class-7 directory already separated from classes 1-3 by the invariant | `ExecPaths.work` (paths.py:149), `_separate` (isolation.py:248) |
| Path containment | `_within` / `_norm` (isolation.py); `_inside` (manager.py:839) |
| Reaching the node's isolation authority without assuming one | the `getattr` pattern of `_isolation_record` (manager.py:701-707) |
| Removing a linked worktree Core created | `LocalNode.remove_worktree` (local.py:382) |
| Charged refusal when a workspace cannot be made | `X.refuse(stop_reason='workspace')` (manager.py:189-192) |

## 7. Open questions for the owner or the design (not answered here)

1. **Pre-dispatch isolation fact.** What tells `dispatch_task` that an execution will run isolated, when today that is decided per execution at spawn (isolation.py:552)? Is `production_dispatch_enabled()` the intended trigger for W5?
2. **Refusal state.** The Task state and `failure_class` for a structural workspace refusal (ADR-0053 "Not decided here": P8's and P11's).
3. **Location and continuity.** Per-execution workspace (class 7, e.g. `own/work`, which §7.5's "workspace … class 7" and R7's "other executions' state is inaccessible" read toward), or per-task as today? What does a retry (attempt n+1) or a P12 hand-off continuation start from? Today both inherit the earlier execution's uncommitted worktree (local.py:362-363).
4. **Where the recorded base revision lives.** An `Execution` field, an event payload, or Mission state. A field written by `prepare_process` touches T-015's `executions.py`.
5. **Seed-time git.** Does creating the repository and making its first commit, before the execution's first process exists, count as "Core runs git against an execution repository" under A5? The answer decides between the seed candidates in W3.
6. **Hook checks without git.** Once Core may not read the execution repository, what replaces `branch_ok` and the canonicaliser's `branch` / `remotes` context for an isolated execution (manager.py:439-450)? The execution's HEAD is a claim under A5.
7. **Progress digest and checkpoint stat.** A git-free digest of the working tree for `end_state` and `diff_stat` (manager.py:539-545), or one computed from the import commit (W6)?
8. **Enablement order.** W3 enabled only together with W6, or isolated project executions refused until both land?
9. **Migration disposition.** What happens to existing `<ARCHEUS_HOME>/worktrees/` content and its uncommitted work, and to tasks recorded `in_place`? Should the planner stop emitting `in_place` once E is on?
10. **Retention.** How long an execution repository is kept after import. §3.2 "Cleanup" speaks of grants and identity only.
