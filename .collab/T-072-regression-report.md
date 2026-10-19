# T-072 · Combined filtered V1 regression on the integration candidate

Run 2026-10-14 13:51:07 to 14:06:18 (local) by a Claude fork, under the owner's authorization of the same day ("T-072 integration"). The candidate tree was not edited, committed to or checked out.

## Candidate

The candidate is the detached checkout `D:/archeus-pv20-integration`, at HEAD `6bc066852569a03e611ae056ba678b921b2d94f7`. `status --short` was empty before and after the run.

The manifest is copied from the T-072 card's `commits:` line.

The checkout was built from 5dfac53 with two base commits:

| Commit | Source |
|---|---|
| 1c8a64b | f6abc4d, `cherry-pick -x` |
| f5f8a26 | 3257dd0, `cherry-pick -x` |

The producers' own heads were then merged by SHA with `--no-ff`. In first-parent order:

| Merge commit | Merged head | Card(s) | Note |
|---|---|---|---|
| 1738013 | e5f77aa | T-048 K1, T-066 K2, T-067 K3 | |
| bebfe55 | 97797de | T-055/T-056/T-061 A6 chain | `local.py` union |
| 003b8f6 | a430301 | T-057/T-059/T-070, T-074 | |
| 908a73c | 743836f | T-058 | |
| 051dafd | aaddefd | T-060 | |
| a2bee07 | cece71d | T-069 | natural base e95bd2d |
| 1dd19e0 | 24b1322 | T-076 | |
| 6bc0668 | ada596c | T-078 | `executions.py` and `test_execution_units.py` union |

T-080 is not in this candidate.

## Command

Run from `D:/archeus-pv20-integration`. It is the T-045 prefix verbatim, plus `-p no:cacheprovider`, a short `--basetemp` (to avoid the T-077 long-home failure) and `-rfEsx`. The interpreter is Python 3.10.6 by absolute path, with pytest 9.0.3.

```
C:\Users\mab\AppData\Local\Programs\Python\Python310\python.exe -m pytest -m "not real_process" --ignore=tests/v1/integration/test_pv20_isolation_windows.py --ignore=tests/v1/integration/test_pv20_writer_fixture.py --ignore=tests/v1/integration/test_claude_code_live.py --ignore=tests/v1/integration/test_dev_launcher.py tests/v1 -q -p no:cacheprovider --basetemp=D:/t072r -rfEsx
```

Two other Claude forks (T-080 and T-062) were running tests on this machine at the same time.

## Result

**7 failed, 4234 passed, 112 skipped, 3 xfailed, 0 errors. Exit 1. Duration 910.06 s (0:15:10).**

### Failures

| # | Test id | First lines | Rerun |
|---|---|---|---|
| 1 | `tests/v1/integration/test_ui_seams.py::test_a_launch_grant_never_exceeds_the_minters_own_scopes` | `assert (403, 'remote...remote host'}) == (403, 'scope_...': 'control'})` / `At index 1 diff: 'remote_host_required' != 'scope_required'` (test_ui_seams.py:253) | fails |
| 2 | `tests/v1/unit/test_mutation_suites_parse.py::test_every_mutant_parses_once_applied[mutate_p11]` | `AssertionError: ('archeus/core/application/executions.py', '                   charged=not (uncharged or stop), stop_reason=stop or e.stop_reason,')` / `assert 0 == 1` | fails |
| 3 | `…test_every_mutant_parses_once_applied[mutate_p12]` | `AssertionError: ('archeus/core/application/executions.py', "              {'exit_reason': 'handoff', 'exit_code': exit_code, 'charged': guarded is not None,")` / `assert 0 == 1` | fails |
| 4 | `…test_every_mutant_parses_once_applied[mutate_p15]` | `AssertionError: ('archeus/api/server.py', "                if (self.principal['origin'] != 'paired'")` / `assert 0 == 1` | fails |
| 5 | `…test_a_crlf_checkout_mutates_exactly_as_an_lf_one[mutate_p11]` | same anchor as #2 | fails |
| 6 | `…test_a_crlf_checkout_mutates_exactly_as_an_lf_one[mutate_p12]` | same anchor as #3 | fails |
| 7 | `…test_a_crlf_checkout_mutates_exactly_as_an_lf_one[mutate_p15]` | same anchor as #4 | fails |

**Rerun.** The 7 failing ids were rerun once, serially, on 6bc0668, with `--basetemp=D:/t072r2`. All 7 failed again (7 failed, 26 passed, the rest of `test_mutation_suites_parse.py` included). The failures are deterministic, not load-related.

**Classification.** All 7 are defects in a producer head. None is caused by the integration or its two union resolutions.

1. **#2, #3, #5 and #6 come from T-067 K3.**
   - `tools/mutate_p11.py` and `tools/mutate_p12.py` anchor on two lines of `archeus/core/application/executions.py`. K3 rewrote both lines and did not update the mutation tools.
   - Anchor present: in `git show <sha>:archeus/core/application/executions.py` at 5dfac53, d92da8a, 82b53a7 and ada596c.
   - Anchor absent: at d69df39, e5f77aa and 6bc0668.
   - Reproduced in the producer checkout: `D:/archeus-pv20-k3` at e5f77aa, `test_mutation_suites_parse.py`: 4 failed, 28 passed (the same 4 ids).
   - The fix belongs on T-067. Either re-anchor `mutate_p11`/`mutate_p12` to the K3 lines, or keep the mutants meaningful against the new `record_end`/`record_handoff` code.
2. **#4 and #7 come from the R1-A chain, T-059.**
   - `tools/mutate_p15.py` anchors on `if (self.principal['origin'] != 'paired'` in `archeus/api/server.py`.
   - Anchor present: at 5dfac53 and f334113.
   - Anchor absent: at 606d5b6, dcbc848, a430301 and 6bc0668.
3. **#1 also comes from the R1-A chain.** Under R1-A Q4-A, a paired token on loopback now gets `remote_host_required` before the scope check. The test still expects `scope_required`, and the file is unchanged since 5dfac53.
   - Reproduced for #1, #4 and #7 in `D:/archeus-pv20-q4-parity` at a430301, with ui_seams + `test_mutation_suites_parse.py`: 3 failed, 30 passed (the same 3 ids).
   - These ids are not attributed commit by commit inside the chain (606d5b6 / dcbc848 / a430301). The anchor evidence points to 606d5b6. The ui_seams test was not run at 606d5b6 alone.
   - T-059 and T-070 are APPROVED. Their own reported test runs did not cover these two files.
   - The fix belongs on a new R1-A follow-up. It has two parts:
     - Decide whether the test should hold the device on a remote host (keeping the scope assertion meaningful) or assert the new refusal.
     - Re-anchor `mutate_p15`.

### Skips: 112

| Count | Reason |
|---|---|
| 97 | the SPA is not built: `npm ci && npm run build` in clients/app |
| 1 | the SPA is not built |
| 4 | paired clients exist only over the http binding |
| 2 | the SPA exists only over the http binding |
| 1 | the TUI exists only over the http binding |
| 1 | device tokens exist only over the http binding |
| 2 | this account cannot create a symlink: [WinError 1314] (K1 `test_a_symlink_in_the_store_is…`) |
| 1 | this user may not create a symlink here |
| 2 | got empty parameter set for (op) |
| 1 | POSIX file modes |

### Xfails: 3

| Count | Test | Marker |
|---|---|---|
| 1 | `test_adapter_contract.py::test_the_codex_adapter_normalises_a_recorded_stream` | phase:P23 |
| 2 | `test_g08_legacy_import.py::test_importing_a_legacy_home_twice_yields_the_same_world[inprocess/http]` | phase:P22 |

The xfails are the same as on 5dfac53.

### Compared with T-047 (5dfac53)

| Run | Passed | Skipped | Xfailed | Failed | Exit |
|---|---|---|---|---|---|
| T-047 (5dfac53) | 3375 | 110 | 3 | 0 | 0 |
| This candidate (6bc0668) | 4234 | 112 | 3 | 7 | 1 |

The +859 passes are the merged cards' new tests, mostly K1/K2/K3 `test_repo_store` and A6, plus T-060/T-069/T-076/T-078. The +2 skips are the two K1 symlink tests on this account (WinError 1314). Basetemp differs from T-047, which used pytest's default.

## Node (clients/app)

The command is the package.json `test` script, run directly with Node v24.15.0. Nothing was installed: there is no `node_modules` and no network access.

```
node --experimental-strip-types --no-warnings --test "test/*.test.ts"
```

**227 tests: 225 pass, 2 fail, exit 1.**

1. **`test/now.test.ts` (whole file).** It fails with `ERR_MODULE_NOT_FOUND: Cannot find package 'react' imported from …\clients\app\src\graph\wide.ts`. React is not installed. This is environmental.
2. **`test/rowpulse.test.ts:182`, "the rows read the page's reduced motion and its slow frames".**
   - The regex `/reduced: reducedMotion,\n\s+degraded: framesSlow,/` does not match `src/components/ui.tsx`.
   - The working copy is CRLF (`core.autocrlf=true`: `i/lf w/crlf`), while the index is LF. This is environmental.

Both failures reproduce identically on the frozen S2 checkout `D:/archeus-pv20-s2-l` at 5dfac53 (also without `node_modules`, also CRLF): the two files gave 11 pass, 2 fail with the same ids. So neither is a candidate defect.

The parity and present tests in this run pass, including T-074's fixture and T-078's `present.ts` label.

## Ruff

`py -m ruff check . --extend-exclude prototypes` (ruff 0.16.0): **All checks passed.**

## Not run

- POSIX (any test on Linux or macOS).
- The browser/SPA e2e: the SPA is not built, which covers the 98 SPA skips.
- Native Windows isolation (`test_pv20_isolation_windows.py`, ignored).
- The writer fixture (`test_pv20_writer_fixture.py`, ignored).
- The live Claude Code CLI (`test_claude_code_live.py`, ignored).
- `test_dev_launcher.py` (ignored per the T-045 prefix, although 3257dd0 now stubs its SPA check).
- Every `real_process` test (deselected by `-m "not real_process"`).
- The node tests with an installed `node_modules`.
- The tests at the CI `ubuntu` image.
- T-080 (not merged).

## Post-run drift check

| Checkout | HEAD | `status --short` |
|---|---|---|
| `D:/archeus-pv20-integration` | 6bc0668 | empty |
| `D:/archeus-pv20-q4-parity` | a430301 | empty |
| `D:/archeus-pv20-k3` | e5f77aa | empty |

- `git diff --stat HEAD` on the integration checkout is empty.
- The basetemps `D:/t072r`, `D:/t072r2`, `D:/t072r3` and `D:/t072r4` were deleted (rmtree with a chmod onerror; link and reparse roots refused).
- The raw logs (`t072_run.log`, `t072_node.log`, `t072_start.txt`) were moved to the session scratchpad. None was left under `D:/`.
