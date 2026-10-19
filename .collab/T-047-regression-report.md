# T-047 · Provenance fixture fix and filtered V1 rerun

Run by Claude on 2026-10-13 from `D:/archeus-pv20-s2-l`. The only source change is commit `5dfac53` (`tests/v1/integration/test_provenance.py`, helper `_verify`). Nothing was installed, activated or cleaned up. Logs are in the session scratchpad (`t045-r047b.log`).

**Result: the filtered V1 suite PASSED on `5dfac53`: 3375 passed, 110 skipped, 3 xfailed, 0 failed, exit 0.** This is filtered by the exclusions below and is not an unrestricted full-suite pass.

## The fix (5dfac53)

`_verify` now records the execution as exactly not isolated before the simulated finish. It does this through a test-only `tx.update(entities.Execution, …, {'isolated': False})` plus a `mission.updated` event marked `forged_by: test`, the same pattern as `test_verification._isolate`. It then re-reads the row and asserts `(isolated, process_seq) == (False, 1)`. This stands in for what a current Core's `prepare_process` records for an ordinary execution (T-036). The routing rig's `work.record_spawn` records no decision, and A6 guards an unknown one.

The following are unchanged: `verifier='code'`; the M03 and M05 assertions on harness, model, route decision and account; `work.record_spawn`; the A6 `unconfined` predicate; and the start sink. No guard was weakened. Codex reviewed the source portion as APPROVE in `reviews/T-047-5dfac53.md`.

## Runs

| # | Command | Window (+02:00) | Result | Exit |
|---|---|---|---|---|
| 1 | `py -m pytest -m "not real_process" tests/v1/integration/test_provenance.py tests/v1/integration/test_routing.py -q` (before commit) | 2026-10-13 ~17:35 | 31 passed | 0 |
| 2 | Filtered tests/v1 on 5dfac53 | 17:39:05, stopped 17:41 | **NO RESULT**: stopped by Claude at the owner's 17:50 session deadline, leftover pytest process killed | — |
| 3 | Filtered tests/v1 on 5dfac53 | 20:15:39 / 20:28:38 | **3375 passed, 110 skipped, 3 xfailed** in 777.43s | 0 |

Run 3 is the card's T-045 prefix, verbatim, by absolute interpreter path (`C:\Users\mab\AppData\Local\Programs\Python\Python310\python.exe`, Python 3.10.6, pytest 9.0.3):
`-m pytest -m "not real_process" --ignore=tests/v1/integration/test_pv20_isolation_windows.py --ignore=tests/v1/integration/test_pv20_writer_fixture.py --ignore=tests/v1/integration/test_claude_code_live.py --ignore=tests/v1/integration/test_dev_launcher.py tests/v1 -q`

3375 + 110 + 3 = 3488. That equals the T-045 collection count; no collect-only was rerun for this card. Compared with T-045: +2 passed, −2 failed, with skipped and xfailed unchanged. The two that changed are M03 and M05. Nothing was deselected or skipped to obtain this result: the skips are the same 110 as in T-045.

## Before and after run 3

- Before: HEAD `5dfac53f0724a80417bdd5196e7986f5752bb132`. `git status --porcelain --untracked-files=all` showed only `?? tests/v1/integration/test_pv20_writer_fixture.py`.
- After: HEAD is unchanged, the status is identical and `git diff --stat HEAD` is empty. The writer file's sha256 is still `b23bba61a5c2d4e175c9155f228d7796ac45d108ffb88366c0d084d96fc72ef8`, as at T-045 preflight.
- The install guard is autouse (`tests/v1/conftest.py`, `no_installed_runtime_stage`). The opt-ins `ARCHEUS_REAL_BOUNDARY`, `ARCHEUS_REAL_HARNESS` and `ARCHEUS_WRITER_FIXTURE` were absent, as checked at T-045 preflight. The guard did not fire.
- Concurrent work: during run 3, the T-048 fork created the detached checkout `D:/archeus-pv20-k1` from `5dfac53` (registered in this repository's worktree list) and worked only there. The T-049 fork was read-only. Neither changed this tree's HEAD, status or files, per the post-run check.

## Exclusions and limits

Excluded: the `real_process` marker (`tests/v1/unit/test_pv20_private_config.py`), the Windows boundary tests, the writer fixture, the live Claude Code CLI test, and the dev launcher (app not built). Real operations in the run: the existing fixtures' Git in pytest-owned temp repositories and worktrees, and Python fixture subprocesses, both owner-authorised. Not checked beyond the guards: anything outside pytest's basetemp.

Not shown: native confinement, CLI, production behaviour, the excluded files, and the K1 candidate in `D:/archeus-pv20-k1`.
