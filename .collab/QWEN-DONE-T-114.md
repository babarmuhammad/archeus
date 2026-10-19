STATUS: review

Card: T-114 · Merge main (2.8.1) into archeus-v1-rearchitecture: tests and commit
By: Qwen (pi · spark/qwen3.8-flash-next) · 2026-10-19

## Commits

- `c8f5bd5e48c3928ebaa18695cf32f26d1ceccea6` — merge commit in D:/archeus-merge, parents `4d37280` (archeus-v1-rearchitecture) and `3b2ce96` (origin/main, 2.8.1). Subject: "Merge main (2.8.1) into archeus-v1-rearchitecture"; body records main.py kept from the branch (build_launch_command lives in launch.py on the branch) and main's 4e91cb0 change reapplied in launch.py; trailer `Co-Authored-By: Qwen <qwen@spark.local>`.
- Staged by name only: `git add claude_sessions/main.py claude_sessions/launch.py`. No `git add -A`/`.`, no push.

## Accept verification

1. `git -C D:/archeus-merge status` (before commit): mid-merge, only `claude_sessions/main.py` unmerged (UU) plus unstaged `claude_sessions/launch.py`; working-tree main.py identical to branch HEAD (`git diff HEAD -- claude_sessions/main.py` empty → branch side kept, no conflict markers); launch.py carried exactly the 4e91cb0 change (`env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'` replaced by the explanatory comment). After commit: `nothing to commit, working tree clean`.
2. Tests (in D:/archeus-merge, Python 3.10.6):
   - `py -m pytest tests -m "not real_process" -p no:cacheprovider --basetemp=D:/t114 --ignore=tests/v1`
     → `2575 passed, 2 skipped, 2 deselected, 1 warning in 339.40s (0:05:39)`. The single warning is a `PytestUnhandledThreadExceptionWarning: KeyboardInterrupt` deliberately raised by `tests/test_plan_execute.py:558 _boom` — test content, not a failure.
   - `py -m pytest tests/v1/unit -m "not real_process" -p no:cacheprovider --basetemp=D:/t114b`
     → `2556 passed, 1 skipped in 91.38s (0:01:31)`.
   - Accept (2) says "unit+contract", so also run (beyond the named command): `py -m pytest tests/v1/contract -m "not real_process" -p no:cacheprovider --basetemp=D:/t114b`
     → `32 passed, 2 skipped, 1 xfailed in 3.71s`.
3. Commit message as required — `git -C D:/archeus-merge show --stat HEAD` shows the subject/body/trailer above and exactly 15 files: the 14 auto-merged main 2.8.1 files (marketplace.json, CHANGELOG.md, CITATION.cff, codex.py, docs/dashboard.md, packaging/*×6, plugin.json, pyproject.toml, tests/test_codex.py) plus `claude_sessions/launch.py`. main.py is absent from the stat because it equals the branch version (ours kept).
4. No other file changed — `git status --short` empty after commit. `D:/t114` and `D:/t114b` deleted (`ls -d /d/t114*` → no such file).

## Not run

- `tests/v1` beyond `unit` and `contract`: design, e2e, integration, judge, tui — not run (card named only the unit quick check).
- Tests marked `real_process` — deselected by both commands' `-m "not real_process"`.
- CI — not run (PR #6 is CONFLICTING per the card; nothing pushed).
- Push — not run (forbidden by card and README; push by Claude after Codex APPROVE).

## Note for reviewer / Claude

The D:/archeus-merge worktree is on a **detached HEAD** (it was detached before I started; `git status` said "Not currently on any branch"). The merge commit `c8f5bd5` exists only on that detached HEAD — no branch or tag points at it. Creating a ref was outside the card's scope ("Nothing else"), so nothing was created. A GC-safeguarding ref should be made by Claude/the owner before review so the SHA is not orphaned.

No block messages encountered; nothing withheld.
