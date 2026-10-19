# T-122 - CI red on c8f5bd5: causes and fixes

Claude fork, 2026-10-19. Branch `fix/ci-c8f5bd5` in `D:\archeus-t122`, one commit **9473e5e** on c8f5bd5. Not pushed.

## Environment: not the cause

| | green 38657897816 (dccca94, 10-15) | red 39246792936 (c8f5bd5, 10-19) |
|---|---|---|
| ubuntu image | ubuntu-24.04 20261004.327.1 | ubuntu-24.04 20261012.334.1 |
| ubuntu git | 2.55.0 | 2.55.0 |
| windows image | windows-2025-vs2026 20261007.264.1 | same |
| windows git | 2.56.0.windows.2 | same |
| windows py3.12 | - | 3.12.10 |

Git did not change, so no config-based hook (`hook.<name>.command`) or other new Git mechanism is involved. The real cause is the 194 commits between dccca94 and c8f5bd5. They added the five failing test files and the staging and canonicaliser code, and until this run they had only been run on Windows with Python 3.10.

## Per failure

| # | Failure (platform) | Cause | Kind | Fix | Test |
|---|---|---|---|---|---|
| 1 | integration `test_the_pinned_store_runs_nothing_the_world_configures`: `AssertionError: e-post-commit` (ubuntu, macos) | Hook sentinels were written with `write_text` and no execute bit. POSIX Git skips a hook that is not executable, so the positive control never fired. It also meant the negative check ("the pinned store fires nothing") proved nothing on POSIX. | test assumption | `_sentinel_hook()` writes the hook and runs `chmod 0o755`. Used for all `hooks-g/e/l` sentinels and for the project's own `.git/hooks/post-checkout`. | same test |
| 2 | integration `test_a_seed_holds_exactly_the_tree_and_runs_nothing_the_world_configures`: `{'e-post-checkout','g-smudge'} <= {'g-smudge'}` (ubuntu, macos) | Same as 1 | test assumption | same as 1 | same test |
| 3 | integration `test_a_junction_planted_in_staging_refuses_the_rename`: expected `alias`, got `not the plain entry expected` (ubuntu, macos) | `staging._entry` treated only a Windows reparse point as an alias. A POSIX symlink was still refused, but with the generic wrong-type message. | product message (the refusal was already correct) | `_entry` now raises `an alias, never followed` for `S_ISLNK` as well. The symlink comment it replaced is gone. | same test; unit alias tests unchanged and passing |
| 4 | unit `test_pv20_runtime_stage::test_a_source_that_changes_while_it_is_copied_refuses[2-...]`: got `changed after it was planned` (ubuntu, macos) | The test faked the Nth `os.lstat` of `Lib/os.py`. `posixpath.realpath` (in `_inside`) also calls `os.lstat`, so the count was off by one on POSIX. | test assumption | The test now wraps `staging._entry` and counts calls there. | same test, both params |
| 5 | unit `test_repo_store::test_a_file_that_is_not_the_one_walked_stops_the_stream_before_done[replaced]`: `DID NOT RAISE` (ubuntu only) | The test removed `a.txt` and then created a new file of the same size. ext4 reuses the freed inode immediately, so `(dev, ino, size)` matched the walk. | test assumption | The replacement is written to `a.txt.new` before the old file goes, then `os.replace`'d in. The new file always gets a different inode. | same test |
| 6 | integration `test_settings_sources::test_T105_a_process_already_gone_is_not_taken_in_...` (ubuntu only) | `kill_pid_tree` sends SIGTERM, which POSIX delivers asynchronously. `boot()` ran while the process was still alive and adopted it. Zombies are already treated as gone (`proc._zombie`). | test race | Asserts the kill was issued, then `_wait_dead(node.alive(...))` before `boot()` | same test (not reproduced locally: timing) |
| 7 | unit `test_execution_units::test_a_path_the_os_cannot_resolve_is_unclassified_not_an_error` x3 (windows 3.12, 3.13, 3.14) | CPython 3.12.10+ on Windows no longer raises from non-strict `realpath` on a NUL or an over-long path (gh-106242). The canonicaliser had relied on that raise to produce one unclassified exec, so these paths came out as ordinary read/write actions. That is a weaker classification than P20 D12 requires. | **product bug** (policy classification; interpreter-version dependent) | `workspace_path` refuses a path containing NUL or longer than 32767 characters itself, on every interpreter, and `canonicalise` maps that to one unclassified exec. This covers the `~` branch and Bash arguments, since both route through `workspace_path`. | Same test, now 4 inputs x {real realpath, tolerant realpath}. The over-long case no longer skips on POSIX. |
| 8 | judge `test_s10b_loop_guard::test_three_escalations_suspend_the_automation[http]`: 30 s `wait_for` timeout (windows 3.12 only) | **Not found.** Normally takes 4-7 s (6.17 s on the same job in the green run). The same job's `[inprocess]` variant took 9.66 s, so that runner was slow. Core stayed non-idle for the whole 30 s. 8/8 serial local passes, 5-8 s each. A parallel stress attempt hit WinError 10048 port reuse between the copies, which is an artifact of the stress setup, not the test. | flake, root cause unknown | none (no speculative change) | - |
| 9 | v1-client e2e `test_spa_marker::test_the_marker_travels_once...` (`marker reaches the task, not restarted: None`) and teardown ERROR `Browser.close: Response has been disposed` (ubuntu) | Pre-existing intermittent failure of the Linux headless graph e2e tests. 38585243719 failed the same test at a different check, and 38646019877 / 38585243719 failed `test_spa_now` and `test_spa_p16`. No graph client code changed since dccca94. 3/3 local passes on Windows. | flake, pre-existing | none | - |

## Verification

- Windows, Python 3.10.6: the five affected files give 1100 passed, 3 skipped.
- Linux container (`python:3.12-slim-trixie`, git 2.47.3, non-root user):
  - fixed tree: 1095 passed, 8 skipped;
  - the same files at c8f5bd5: failures 1-5 reproduce exactly (5 failed). 6 did not reproduce there, because it is timing-dependent.
- With the hooks executable, the pinned store and the seed workspace still fire no world-configured hook on Linux (global include, `GIT_CONFIG_*` environment, the source repo's own `core.hooksPath`/fsmonitor, filters, `uploadpack.packObjectsHook`), and the positive controls do fire. On POSIX this is the first run in which those assertions actually test something.
- e2e `test_spa_marker.py`: 3/3 on Windows with ARCHEUS_E2E=1. The SPA was built in the worktree and its output is gitignored.
- ruff: all changed files pass.

## Not done / for the parent

- Not pushed. CI has to confirm on push, especially failure 6 (race) and the macOS legs.
- Failure 8 (loop-guard judge timeout) and failure 9 (Linux graph e2e) are flakes. Each could become its own card if it recurs. Failure 9 has failed in 3 of the last 5 PR runs.
- Out of scope, noted only: `manager._inside` (manager.py:1095) also calls `realpath`, and a NUL path there no longer raises on new CPython. It returns a `commonpath` answer instead of `False`. Worth a look in the same light as failure 7.
- Docker Desktop was started on this machine to run the Linux container, and has been left running.
- Review: failure 7 changes policy classification, and failure 3 touches `staging._entry`, which `local._plain` also uses. The card asks for a Codex aimed review whenever the repo store or isolation/boundary code is touched.

## Correction r1 (2026-10-19, Claude fork) - Codex CHANGES on 9473e5e

Review: `reviews/T-122-9473e5e.md`. Both findings are fixed in commit **ca2ca4b** on `fix/ci-c8f5bd5`, on top of 9473e5e. Not pushed.

- Finding 1, `canonical.py`: the length check counted code points, and only of the expanded argument.
  - `canonical.openable(path)` is now the single check, run on the effective path before any `realpath`.
  - It refuses a NUL, more than 32767 units in total, or any component longer than 255 units. Units are UTF-16 on Windows and bytes elsewhere. Components are split on `\` and `/` on Windows, `/` elsewhere.
  - `workspace_path` applies it to the joined `workdir/path`, to `workdir` itself, and to the `~` form. A failing path becomes one unclassified exec.
- Finding 2, `manager.py` `_inside`: both arguments now go through `canonical.openable` before `realpath`. A cwd or root that no OS can open hits the existing `ValueError` branch, so `_inside` returns `False`.
- Tests (`tests/v1/unit/test_execution_units.py`), each run with real `realpath` and with a monkeypatched tolerant one (identity, standing in for CPython >= 3.12 on Windows), so they bite on 3.10 too:
  - **unclassified-path test, 4 new cases:**
    - a path that fits alone but not once joined to the workspace;
    - a 256-character component, via Write and via Bash;
    - `ASTRAL`: 271 components of 60 U+1F600. That is 16530 code points, about 32790 UTF-16 units, and every component stays under 255 on every platform.
  - **inclusive limits:** a 255-character component and a 32767-unit path pass. A joined path of exactly 32767 still reads as `read`. One unit more is refused.
  - **`_inside` with invalid paths:** a workspace-prefixed cwd holding a NUL, a 256-character component or an over-long tail is never inside. Neither is anything under a root that holds a NUL. A plain subdirectory still is.
- Verification:
  - with the 9473e5e versions of the two product files put back temporarily, 8 of the new cases fail. With ca2ca4b they pass;
  - `test_execution_units.py`: 347 passed on Windows (Python 3.10.6), and 347 passed in the Linux container (Python 3.12, as non-root);
  - ruff clean on the three changed files.
- Still not covered, as Codex also listed: UNC and `\?\` prefixes, trailing dot or space, alternate data streams, and device names. They are not explicitly refused, and no bypass through them was shown.
- Process note: during the bite check I ran `git checkout --` on the test file, which discarded my own uncommitted edit to it. I rewrote it before committing. Nothing else was touched.
