# T-079 · A shorter Core-owned worktree layout: contract before code

Claude (fork), 2026-10-14. Contract only: no code, no canonical document, no test, no commit. Owner chose option C of `T-077-long-home.md` §6 (with A and B, which are T-078). Source read at `5dfac53` through the read-only checkout `D:/archeus-pv20-s2-l`.

## 1. Today's template and its budget

Built in two places, both from ids, never from a stored path:

- task: `<home>\worktrees\<project_id>\<mission_id>\<task_key>` (`archeus/core/execution/manager.py:387`)
- mission: `<home>\worktrees\<project_id>\<mission_id>\_mission` (`archeus/core/verification/worker.py:47-48`)

`project_id` is `prj_` + a 26-character ULID (30 characters), `mission_id` is `msn_` + 26 (30). The task key is minted by Core as `t%d` (`archeus/core/planning/planner.py:268`): `t1`…`t9` are 2 characters, `t10`…`t99` 3, and so on.

Lengths after `<home>`, with `\` counted:

| Path | Arithmetic | After home |
|---|---|---|
| task root (`t1`) | `\worktrees` 10 + `\prj_…` 31 + `\msn_…` 31 + `\t1` 3 | **+75** |
| task `.git` | root + `\.git` 5 | **+80** |
| mission root | 10 + 31 + 31 + `\_mission` 9 | **+81** |
| mission `.git` | root + 5 | **+86** |

Two caps (T-077 §3, measured on Git 2.49.0.windows.1):

- **L1, `.git` ≤ 220 characters** (`'$GIT_DIR' too big`; `core.longpaths` does not lift it). That puts the cap on `ARCHEUS_HOME` at **140 for a task** (220 − 80) and **134 for the mission worktree** (220 − 86). T-077's bisection stopped at 140 because the task worktree fails first. The mission worktree is the tighter limit today.
- **L2, a checked-out file ≤ 259 characters** (`core.longpaths` lifts it, which T-078's option B does for Core's own `worktree add`). The room left for a tracked file's repository-relative path is 259 − root − 1:

| Home | Length | Task: L1 `.git` | Task: L2 room | Mission: L1 `.git` | Mission: L2 room |
|---|---|---|---|---|---|
| default `C:\Users\mab\AppData\Local\Archeus` | 34 | 114 ok | **149** | 120 ok | **143** |
| long (T-077 failing run) | 141 | 221 **FAIL** | 42 | 227 **FAIL** | 36 |
| 160 | 160 | 240 **FAIL** | 23 | 246 **FAIL** | 17 |

## 2. A shorter template

The project segment carries no identity: a mission belongs to one project, and a mission ULID is unique on its own (minted monotonic within a process, `archeus/core/domain/ids.py:55-77`). The `prj_`/`msn_` prefixes only repeat what the position already says. Three candidates, all staying under the existing `worktrees/` entry, so `V1_OWNED`, the §5.1 table's entry list and `test_paths`' entry check (`tests/v1/unit/test_paths.py:117-132`, which reads only top-level names) are unchanged.

| Option | Template | Task `.git` | Mission `.git` | Home cap (L1, binding = mission) | L2 room at default home (task / mission) |
|---|---|---|---|---|---|
| **S, mission ULID (recommended)** | `worktrees\<mission ULID, 26>\<task_key>` and `…\<ULID>\_mission` | +45 | +51 | **169** (was 134) | **184 / 178** (was 149 / 143) |
| H, hash | `worktrees\<8 base32 chars of sha256(mission_id)>\…` | +27 | +33 | 187 | 202 / 196 |
| F, flat | S with `w\` instead of `worktrees\` | +37 | +43 | 177 | 192 / 186 |

- **S** maps 1:1 and reversibly to the mission (prefix `msn_` back on). It's collision-free by construction because ULIDs are unique, and stable because it depends only on the mission id. It saves 35 characters on L1 and L2.
- **H** saves another 18, but 40 bits per home is a probability, not a guarantee. It would need an ownership marker and a refusal when the marker names another mission: new code and a new failure mode, for 18 characters.
- **F** saves 8 over S, but `w` is a new top-level entry. That's a `V1_OWNED` change, a new §5.1 row, a `test_paths` change and a reset-list decision. Not worth 8 characters.

Recommendation: **S**. Arithmetic for S: task root = `\worktrees` 10 + `\<26>` 27 + `\t1` 3 = +40; `.git` +45. Mission root = 10 + 27 + `\_mission` 9 = +46; `.git` +51. L1 cap 220 − 51 = 169. L2 room at default home: 259 − (34 + 40) − 1 = 184 for a task, and 259 − (34 + 46) − 1 = 178 for the mission. Long keys: each extra key character costs one (`t10` −1, `t100` −2).

## 3. Upgrade under keep-all: Core reads both layouts

Existing worktrees are never moved, renamed or deleted by the upgrade. **Old-first lookup is mandatory, not a courtesy.** Today both sites re-derive the path on every use, and the task branch `archeus/<msn>.<key>` is checked out at the old path. If a new path were computed while an old worktree exists, `git worktree add` would refuse the branch as already checked out elsewhere, and that refusal would travel the charged `workspace` path (`manager.py:222-226`) on every attempt. That's exactly T-077's failure, for a different reason.

The rule: one resolver per kind, used by every site. It returns the **legacy path if it exists as a directory**, else the new path:

- `task_worktree(project_id, mission_id, key)`: legacy `worktrees\<project_id>\<mission_id>\<key>`, new `worktrees\<ULID>\<key>`.
- `mission_worktree_path(project_id, mission_id)`: legacy `…\<project_id>\<mission_id>\_mission`, new `worktrees\<ULID>\_mission`.

"Exists as a directory" is exactly the test `LocalNode.add_worktree` and `mission_worktree` already apply to say "this one is mine, made before a restart" (`archeus/node/local.py:361-362`, `459-460`). Its meaning is unchanged.

Per path:

- **Resume and restart:** `manager._workspace` runs on every process start, resumes included (`manager.py:222`). It goes through the resolver and finds the old directory. Readers that use the recorded `e.workdir` (`manager.py:485`, `597`; `worker.py:179`, `307-308`) are untouched: they never re-derive.
- **A new attempt of a task already started before the upgrade:** legacy found, same as a restart. A task first started after the upgrade gets the new path.
- **A mission split across the upgrade:** task worktrees may sit in both layouts, and the mission worktree stays wherever it was first made. Each lookup is per path, so a mix is fine.
- **Merge-back:** `worker.py:296` (create/find) and `worker.py:330` (read its head) MUST both use the resolver. If only `:296` did, `:330` would read the new, absent path, `git_head` would return None, and `note_integration_head(None)` would mark the verified head stale for every mission begun before the upgrade.
- **Removal:** `remove_worktree(root, e.workdir)` (`worker.py:308`) uses the recorded path, so it's unchanged. Git's admin dir in the user repository (`.git/worktrees/<basename>`) is keyed by basename (`t1`, `_mission`), which the layout doesn't change.
- **T-027 / T-016:** an isolated execution is refused before any worktree is computed (`manager.py:362-374`), and K2's seeded workspace lives under `run/` via `ExecPaths`, not `worktrees/`. Neither is touched. K2's own 259-character refusal is its own limit.
- **Reset:** `worktrees/` stays one V1 entry, and a reset removes it whole in either layout. No reset-list change.

## 4. Every site that builds or parses a worktree path (5dfac53)

| Site | Role | Change |
|---|---|---|
| `archeus/core/execution/manager.py:387` | builds the task path | call `task_worktree(...)` |
| `archeus/core/verification/worker.py:47-48` `_mission_wt` | builds the mission path | delegate to `mission_worktree_path(...)` |
| `archeus/core/verification/worker.py:296` | create/find mission worktree | via `_mission_wt`, unchanged call |
| `archeus/core/verification/worker.py:330` | read mission head | via `_mission_wt`, unchanged call |
| `archeus/node/local.py:357-378` `add_worktree`, `:456-468` `mission_worktree`, `:381-389` `remove_worktree` | take a path, build none | none (T-078 edits these for A/B) |
| `archeus/infra/paths.py:28-29` `V1_OWNED` | names `worktrees` | none |
| `tests/v1/integration/test_verification.py:127`, `:315`, `:949` | hardcode the legacy mission template | use the resolver |
| `tests/v1/integration/test_verification.py:463`, `:496`, `:510`, `:519`, `:834-848`; `tests/v1/unit/test_execution_units.py:1000-1001`, `:1211-1213` | fake or call `add_worktree` with their own paths | none expected |

No reader parses a worktree path back into ids. The TUI and API carry `workspace_mode` (`clients/app/src/api/generated.ts:754`) but never the path. `claude_sessions/worktrees.py` and `repos.py` are the legacy GUI's view of user repositories, not V1's `worktrees/`. Documents naming the template, all canonical, so append-only: `execution-architecture.md:319`, `p11-design-gate.md:613`, `p13-design-gate.md:107` and `:394`, `pv13-windows-os-confinement-study.md:69`, `pv20-execution-isolation-design.md:123`, `target-architecture.md:137` and `:215`.

## 5. Canonical amendment (for the implementation card; append, never reword)

To append after the §5.1 table in `docs/architecture/target-architecture.md`, as a dated "as built" amendment:

> **Amendment 2026-10-xx (T-0xx, worktree layout).** New task worktrees are created at `<ARCHEUS_HOME>/worktrees/<mission ULID>/<task-key>` and the mission worktree at `<ARCHEUS_HOME>/worktrees/<mission ULID>/_mission`, where `<mission ULID>` is the mission id without its `msn_` prefix. The project segment and the id prefixes are dropped because Git on Windows refuses a worktree whose `.git` path passes 220 characters (`'$GIT_DIR' too big`, measured, T-077). The old layout capped `ARCHEUS_HOME` at 134 characters, and the new one at 169. Worktrees created under the earlier layout `<ARCHEUS_HOME>/worktrees/<project-id>/<mission-id>/<task-key>` (and `…/_mission`) are kept where they are and still used: Core looks for the earlier path first and uses it when it exists. Nothing is moved or deleted by the change. `worktrees/` remains one V1 entry. Its ownership, keep-all and reset behaviour are unchanged. The layouts recorded in `execution-architecture.md` §(workspace), `p11-design-gate.md` (workspace table), `p13-design-gate.md` (§8, §12.1), `pv13-…` and `pv20-execution-isolation-design.md` describe worktrees created before this amendment.

Plus a one-line "as built" pointer to that amendment appended in each of the five documents listed in §4. Whether those pointers are required or the §5.1 amendment alone suffices is Q3.

## 6. Implementation card

**T-0xx · New worktrees use the short layout; old ones are still found**

- **auth:** owner, naming the canonical amendment (Q3) and option S/H.
- **scope:** a detached checkout from the integration base the owner picks (T-072 chose frozen S2 + `f6abc4d` + `3257dd0`), or from `5dfac53` if this lands before integration. Files:
  - `archeus/infra/paths.py`: the two resolvers, next to the other path helpers; no `V1_OWNED` change.
  - `archeus/core/execution/manager.py:387`
  - `archeus/core/verification/worker.py:47-48`
  - `tests/v1/unit/test_paths.py`: resolver cases.
  - `tests/v1/integration/test_verification.py`: `:127`, `:315`, `:949` via the resolver, plus the new tests.
  - `docs/architecture/target-architecture.md`: the §5 amendment, appended.
  - The other five documents' pointers, if Q3 says so.

  It touches `manager.py`, which T-078 also edits (`:222-226`, a different hunk) and which K3/T-067 edits too. Claim it after T-078 or rebase it onto T-078.
- **accept:**
  1. A task or mission first started after the change uses `worktrees\<ULID>\<key>` / `…\_mission`.
  2. When the legacy directory exists, the legacy path is returned. That holds for a resume, a restart, a new attempt of a pre-upgrade task, merge-back create (`:296`) and merge-back head read (`:330`). A mission with task worktrees in both layouts verifies and merges.
  3. Nothing moved or deleted. No `V1_OWNED` or reset change.
  4. At `ARCHEUS_HOME` length 169 a mission runs and merges, and at 170 the mission worktree hits L1. With T-078 that gives one uncharged `path_too_long`.
  5. All existing execution and verification suites pass unchanged, except the three hardcoded legacy paths.
- **verify:**
  - Unit tests on both resolvers: legacy absent → new; legacy present → legacy; legacy present as a file → new (only a directory counts, as today).
  - Integration on pytest-temp Git: a mission started under a forced legacy layout, then continued with the new code. It resumes in the old task worktree, merges through the old `_mission`, and `:330` reads the right head.
  - T-077's bisection repeated: home 169 passes and 170 refuses.
  - Mutants: the resolver checks new first; `:330` keeps the inline template; the project segment kept; `msn_` kept; a legacy file is taken as a worktree.

## 7. Owner questions

1. **Template: S (recommended), H or F?** S is collision-free with no new code path and lifts the cap from 134 to 169. H buys 18 more characters with a collision check. F needs a new top-level entry.
2. **Is S enough headroom?** At 169 a user needs an `ARCHEUS_HOME` override deeper than 169 characters to hit L1, and the default home is 34 here. Recommended: yes, combined with T-078's A, which turns any remaining overflow into one clear uncharged refusal.
3. **Canonical amendment: the §5.1 amendment only (recommended), or also an "as built" pointer in each of the five documents that print the old template?** The pointers keep each gate readable on its own, at the cost of six appended edits instead of one.
4. **Order relative to T-078 and integration (T-072):** recommended after T-078 is reviewed, so the resolver's new path is covered by T-078's length check from the start, and before the T-072 integration so the merged tree carries one layout rule.

## What I read or ran

- Read with `sed`/`grep` in `D:/archeus-pv20-s2-l` (5dfac53, nothing written there):
  - `archeus/core/execution/manager.py` (205-232, 359-393)
  - `archeus/core/verification/worker.py` (35-60, 290-336)
  - `archeus/node/local.py` (357-389, 456-468)
  - `archeus/infra/paths.py` (20-40)
  - `archeus/core/domain/ids.py`
  - `archeus/core/planning/planner.py` (268)
  - `docs/architecture/target-architecture.md` (137, 205-222)
  - `tests/v1/unit/test_paths.py` (117-132)
  - grep results over `archeus/`, `claude_sessions/`, `tools/`, `tests/`, `clients/app/src` and `docs/`
- Also read `.collab/T-077-long-home.md` and the T-079 card.
- No test or Git command beyond `git rev-parse` and `grep`.
- The figures are T-077's measurements combined with string arithmetic. No new probe was run.
