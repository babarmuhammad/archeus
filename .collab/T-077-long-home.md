# T-077 · A long ARCHEUS_HOME stops every worktree execution at workspace creation

Claude (fork), 2026-10-14. Investigation only: no product or test file edited, nothing committed. Tree: `D:/archeus-pv20-longhome`, detached at `5dfac53`. Git 2.49.0.windows.1, Python 3.10, Windows 11 with `LongPathsEnabled = 1`, `core.longpaths` unset in every git config.

## 1. Short answer

The failure is **not silent**, and **verification is not where it happens**. Each execution dies before it starts: `git worktree add` refuses the task's worktree because a path is too long. Core records that as a charged `workspace` refusal, retries it, fails the task, replans twice (two real planner calls), and parks the mission `BLOCKED`. The tests then see a Core with nothing left to do, and `pump` reports *"Core went idle before the awaited state"* (`tests/v1/integration/test_verification.py:57`). That message is the test rig's, not Core's.

There are two separate limits, and a real user can hit the second with the default `ARCHEUS_HOME`:

1. **`'$GIT_DIR' too big`**: the new worktree's `.git` path must be at most **220** characters. With Core's layout that means `ARCHEUS_HOME` must be at most **140** characters. `core.longpaths=true` does not lift this one.
2. **`Filename too long` / `Could not reset index file`**: a tracked file whose checkout path passes 259 characters. With the default home on this machine, that is any repository path longer than about **149** characters. `core.longpaths=true` does lift this one.

## 2. Reproduction (what ran)

Single test, `tests/v1/integration/test_verification.py::test_V09_forged_evidence_is_refused`, with `-q -p no:cacheprovider`:

| basetemp | ARCHEUS_HOME length | result |
|---|---|---|
| `<session scratchpad>/t077/bt_long_xxxxxxxxxxxxxxxxxxxxxxxxxxx` | 182 | 1 failed: "Core went idle before the awaited state" |
| `D:/t077/s` | short | 1 passed |
| pytest default | short | 1 passed |

**Threshold, by bisection** (`scratchpad/t077/bisect.py`; basetemp `D:/t077/<padding>`, so `ARCHEUS_HOME = <basetemp>/test_V09_forged_evidence_is_re0/archeus-home`): 9 runs, at lengths 60 pass, 182 FAIL, 121 pass, 151 FAIL, 136 pass, 143 FAIL, 139 pass, 141 FAIL, 140 pass. **The test passes at 140 and fails at 141.** T-075's 149 is on the failing side.

**What Core recorded.** I instrumented a scratchpad copy of the tree (`git archive HEAD`, never the checkout): `pump` dumped the entity rows and the last 40 events before asserting. At 182 every execution is `ABANDONED` with trigger `spawn_failed`, and the task's three plans each ended `FAILED` with `failure_class: execution`. The mission went `EXECUTING → REPLANNING` twice (with `archeus_call.ended purpose planner` each time), then `REPLANNING → BLOCKED` with `replan_budget_exhausted`. Reasons read back from `archeus.db`:

- home 141, 143 and 151: `no workspace: git worktree add failed: … fatal: '$GIT_DIR' too big`
- home 182: `no workspace: git worktree add failed: Preparing worktree (resetting branch 'archeus/<msn>.t1'; was at …) fatal: could not create leading directories of '<home>/worktrees/prj_<26>/msn_<26>/t1/.git': Filename too long` (that full path is 262 characters)

## 3. The path that hits the limit

`archeus/core/execution/manager.py:387` builds the task worktree as `os.path.join(archeus_home(), 'worktrees', m.project_id, m.id, t.key)`. Project and mission ids are 30 characters each (`prj_` / `msn_` plus a 26-character ULID), so the worktree root is **home + 75** for a two-character task key such as `t1`, and its `.git` is **home + 80**. The task key is plan data, so it can be longer than that.

**Limit 1 checked against plain Git** (`scratchpad/t077/gitlimit.py`, with global and system config off): `git worktree add` to a path whose `<path>/.git` is 219 or 220 characters gives ok; 221 or 222 gives `fatal: '$GIT_DIR' too big`. With `-c core.longpaths=true`, 221, 230 and 240 all still fail the same way. The number fits Git's `PATH_MAX - 40` with PATH_MAX at 260, but I did not read Git's source for it. So 220 is measured, not cited. 140 + 80 = 220 matches the bisection exactly.

**Limit 2 checked against plain Git** (`scratchpad/t077/deepfile.py`): the default home on this machine is `C:\Users\mab\AppData\Local\Archeus` (34 characters), so a worktree root there is 109 characters. Using a worktree root of exactly that length and one tracked file whose checkout path is 270 characters:
- without `core.longpaths`: FAIL, `fatal: Could not reset index file to revision 'HEAD'.`
- with `-c core.longpaths=true`: ok.

## 4. Where it is handled, and what is wrong with that

- `archeus/node/local.py:373-377` (`LocalNode.add_worktree`) runs `git worktree add` and raises `OSError('git worktree add failed: <git stderr>')`. The same pattern sits at `local.py:463-466` (`mission_worktree`).
- `archeus/core/execution/manager.py:222-226` catches it and calls `X.refuse(..., reason='no workspace: %s' % err, stop_reason='workspace')`.

Nothing is swallowed: the reason, including Git's text, is in the execution and task events. What is wrong is the **classification**. A path-length refusal is deterministic for a given home and repository, yet it travels the charged, retryable `workspace` path. So:
- the task uses up every attempt and is labelled `failure_class: execution`;
- the mission spends its replan budget, two real planner calls here, on a problem no plan can fix;
- the user ends up with a `BLOCKED` mission whose top-level reason is "no replan left for this mission", with the cause three events down.

T-049 already noted that this charged `workspace` path is an interim choice (`T-049-seed-contract.md`, the no-predecessor-import refusal).

## 5. Can a real user hit it?

- **Limit 1 (home ≤ 140):** not with the default home. `%LOCALAPPDATA%\Archeus` is 34 characters here, and stays under 140 unless the Windows user name runs past about 100 characters. It does apply when `ARCHEUS_HOME` is set explicitly to a deep folder, which is how the test suite and any nested tool home reach it. Any task key longer than `t1` lowers the ceiling one-for-one.
- **Limit 2 (deep files):** yes, with the default home. Any project with a tracked file deeper than about 149 characters from its root fails every execution, unless the user's own git config sets `core.longpaths=true`. Long Java or .NET package paths and nested `node_modules` committed to the repo are the usual way to get there. With a longer user name the room shrinks one character per character.
- **Out of scope here:** the K1/K2 store and seed path (`repos/`, `repos/.seed/`, T-048/T-066) has its own layout, and I did not measure it. K2 writes the seed with Python, and Python has `LongPathsEnabled` but not Git's `$GIT_DIR` cap. K2's `_Manifest` already refuses a path over 259 characters, by design.

## 6. Proposed fix card (owner chooses; nothing decided here)

**T-0xx · A workspace Git cannot build is refused at once, uncharged, with its reason.**

- **Files:** `archeus/core/execution/manager.py` (the `_workspace` refusal at `:222-226`), `archeus/node/local.py` (`add_worktree`, `mission_worktree`), possibly `archeus/infra/paths.py` (a shorter worktree layout, option C), and `tests/v1/unit/test_execution_units.py` plus an integration test running under a long home.
- **Options (not exclusive):**
  - **A. Fail loudly, once.** Before `git worktree add`, compute `len(<worktree>/.git)` and refuse above 220 with a new non-charged `stop_reason` (for example `path_too_long`) whose reason names the path, its length, the limit, and the fix: a shorter `ARCHEUS_HOME`. No retry and no replan. The mission is blocked on a reason a user can act on. This doesn't cover limit 2, which is per file.
  - **B. Pass `-c core.longpaths=true`** to every Core-run `git worktree add` (and to `git worktree remove`). That lifts limit 2 for checked-out files without touching the user's config. It does nothing for limit 1. One open question: whether tools later run inside that worktree (the harness, the user's own git) cope with paths over 260. They read the user's config, not Core's `-c`.
  - **C. Shorter internal names.** For example `worktrees/<project short id>/<mission short id>/<task>`, or a fixed-length hash. That widens the headroom for both limits by up to about 50 characters. It changes a Core-owned layout under `worktrees/` (target-architecture §5.1 keep-all and existing worktrees after an upgrade), so it needs its own decision and probably a canonical note.
  - **D. Classify deterministic Git refusals as uncharged** in general (a `stop_reason` for a workspace Git rejects up front, for any reason), rather than special-casing length. This is wider, and overlaps the interim `workspace` path T-049 already flagged.
- **Accept (for whichever is picked):** at `ARCHEUS_HOME` length 141, the V09 scenario ends with one uncharged refusal whose reason names the path length and the limit. There are no retries and no planner calls, and the mission state tells the user what to change. A tracked file at 270 characters under the default-length root either checks out (B) or is refused once with its path (A without B). Everything at length 140 and below behaves as today.
- **Verify:** the bisection above (passes at 140 must still pass); a unit test on the length check; an integration test with a long basetemp; the deep-file probe as a test on pytest-temp repositories. A synthetic home is enough for all of it, and none of it needs a real user path.

## 7. What did not run

- The judge verification scenarios under a long home. T-075 saw them fail the same way, and I didn't rerun them.
- macOS and Linux, where Git has no 260 cap: limit 1 is Windows only.
- Git versions other than 2.49.0.windows.1.
- Git's source, so the 220 figure is measured, not cited.

Scratch files: `scratchpad/t077/` (the copy, the logs, `bisect.py`, `gitlimit.py`, `deepfile.py`). `D:/t077` was created for the short basetemps and the Git probes, and has been deleted (Python rmtree, clearing read-only bits). `git status` in the checkout is clean.
