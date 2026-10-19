# T-045 · Final S2 interim regression on the reviewed combined tree

Validation only. Run by Claude on 2026-10-13 from `D:/archeus-pv20-s2-l`. No application or test source was edited, nothing was installed, committed, activated or cleaned up. Logs are in the session scratchpad (`t045-five.log`, `t045-collect.log`, `t045-suite.log`).

**Result: the five-file regression PASSED; the filtered V1 suite FAILED with 2 failures.** Both failures trace to T-042's start sink (`c9e9e28`) and a test rig that never records an isolation decision, not to T-044. A corrective scope is named below. Under this card, the failures stop validation and no fix was made.

## Preflight (before collection)

- HEAD `9e4443fd569a5a6756383aaeab3a71f9a40509d1`, which matches the card. `git status --porcelain --untracked-files=all` shows only `?? tests/v1/integration/test_pv20_writer_fixture.py`, and `git diff --stat HEAD` is empty. The untracked writer file was kept: sha256 `b23bba61a5c2d4e175c9155f228d7796ac45d108ffb88366c0d084d96fc72ef8`, 49241 bytes, dated Oct 11. The hash was identical after every run.
- The install guard is present and autouse: `tests/v1/conftest.py` defines `@pytest.fixture(autouse=True) def no_installed_runtime_stage` (T-040, `a16d3c9`).
- Opt-ins were checked by name and presence only. `ARCHEUS_REAL_BOUNDARY`, `ARCHEUS_REAL_HARNESS` and `ARCHEUS_WRITER_FIXTURE` are absent from the process, user and machine environment, and so is `ARCHEUS_HOOK_WAIT`. Their consumers are `test_pv20_isolation_windows.py`, `test_claude_code_live.py` and `test_pv20_writer_fixture.py`; all three are also `--ignore`d. The suite's own `archeus_home` fixture sets `ARCHEUS_HOME` per test, and it is absent from the outer environment.
- Interpreter: `C:\Users\mab\AppData\Local\Programs\Python\Python310\python.exe`, Python 3.10.6, pytest 9.0.3. The same binary that `py` resolves to, bound here by absolute path.
- Ignored caches were left in place (`.pytest_cache/`, `.ruff_cache/`, `__pycache__/`). The card's command does not pass `-p no:cacheprovider`, so pytest's cache was written as usual.

## Runs

Common prefix (the card's, verbatim):
`python.exe -m pytest -m "not real_process" --ignore=tests/v1/integration/test_pv20_isolation_windows.py --ignore=tests/v1/integration/test_pv20_writer_fixture.py --ignore=tests/v1/integration/test_claude_code_live.py --ignore=tests/v1/integration/test_dev_launcher.py`

| # | Appended | Start / end (+02:00) | Result | Exit |
|---|---|---|---|---|
| 1 | `tests/v1/unit/test_pv20_isolation.py tests/v1/unit/test_execution_units.py tests/v1/integration/test_execution.py tests/v1/integration/test_context_capacity.py tests/v1/unit/test_mutation_suites_parse.py -q` | 17:15:52 / 17:16:58 | **778 passed** in 64.20s | 0 |
| 2 | `tests/v1 -q --collect-only` | 17:17:07 / 17:17:09 | **3488 tests collected**, no collection error | 0 |
| 3 | `tests/v1 -q` | 17:17:14 / 17:32:15 | **2 failed, 3373 passed, 110 skipped, 3 xfailed** in 899.33s | 1 |

3373 + 2 + 110 + 3 = 3488, the number collected. After every run, HEAD and `git status` were unchanged, `git diff --stat HEAD` was empty and the writer file hash matched.

Exclusions, as the card states: the `real_process` marker (its one user is `tests/v1/unit/test_pv20_private_config.py`) and the four ignored files. The dev launcher is excluded because the app is not built. This is therefore **not** an unrestricted full-suite pass, and with two failures it is not a filtered pass either.

What the runs executed that was real: the existing fixtures' Git (`init`/`add`/`commit`/`status`/worktree/merge) in pytest-owned temp repositories, and Python fixture subprocesses (the fake harness and the hook script in `test_execution.py`). The owner allowed both for this card. Not observed and not checked beyond the preflight: anything outside pytest's basetemp. No native boundary, provider, CLI or install-staging test ran: they were excluded or not opted in, and the install guard did not fire.

## Failures

1. `tests/v1/integration/test_provenance.py::test_M03_one_model_id_on_two_harnesses_stays_two_harnesses`
2. `tests/v1/integration/test_provenance.py::test_M05_a_fallback_is_its_own_route_decision_and_the_verification_names_it`

Both fail with the same error, raised in `_verify` (`test_provenance.py:29-35`) when it calls `V.start(..., verifier='code', ...)`:

`archeus.core.application.verification.Refused: mission msn_…: verification withheld: its commands would run over content of a mission with isolated or unknown provenance` (raised at `archeus/core/application/verification.py:195`).

**Cause, from reading the source (not re-run in isolation).** These tests use the routing rig (`tests/v1/integration/test_routing.py:60-67`). Its `finish` reports the process through `work.record_spawn` (`archeus/core/application/work.py:371-380`), the P3.5 entry point "for a caller that spawned without `executions.prepare_process`". That call sets `process_seq` to 1 and never records an isolation decision, so the execution keeps `isolated=None`. T-042's derived guard `unconfined` treats an execution with `process_seq >= 1` and `isolated` not exactly False as guarded. That is A6 as the owner decided it ("unknown not ordinary"). So the start sink refuses the `code` verifier, which is the intended behaviour applied to a rig that models no isolation decision.

**Why it was not seen earlier.** T-042's card verify named four files, and `test_provenance.py` is not one of them. The full suite started on `c9e9e28` was stopped before it finished, with no result. The two failures have existed since `c9e9e28`. T-044 (`57a87fd`) does not touch this path.

## Corrective scope proposed (not done here)

Test-only, one file: `tests/v1/integration/test_provenance.py`, helper `_verify`. Before `V.start`, record the execution as ordinary (`isolated=False`), which is what a current Core's `prepare_process` records for an ordinary execution (T-036). Use a forged `tx.update` plus an event, the same pattern as `_forge`/`_isolate` in `test_verification.py`. The `code` verifier and the provenance assertions stay unchanged. Verify with `test_provenance.py` and `test_routing.py`, then rerun the T-045 filtered suite.

Rejected alternatives:
- Switching `_verify` to `generic_human` changes what the test models ("as the worker starts one").
- Making `work.record_spawn` record `isolated=False` changes a production entry point, and would let an unprepared process pass as ordinary, against A6.
- Relaxing the guard for None reopens owner G1/A6.

## Bearing on other cards

- T-044's required regression (run 1, the five-file command) **passed: 778**. That clears T-044's open item.
- The T-042 code stands as approved. The failures are a missing test-rig decision, not a source defect found by this run, and owner or Codex routing decides where the one-file fix goes.
- Not shown by this report: native confinement, CLI, production behaviour, the dev launcher, `real_process` tests, or anything about the excluded files.
