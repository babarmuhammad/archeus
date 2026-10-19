# T-115 · Slice K pre-run on c8f5bd5 — PARTIAL

Claude fork, 2026-10-19, checkout `D:\archeus-t115` (detached at `c8f5bd5`, the pushed candidate that replaces
`4d37280`). Read-only on product code; no commits. Stopped early by the owner (wrap up by 18:40 local), so the
mutation pass is incomplete: see section 3.

## 1. tests/v1 with ARCHEUS_E2E=1 (SPA built offline first)

Command: `ARCHEUS_E2E=1 py -m pytest tests/v1 -q -rfEsxX --basetemp=<scratchpad>\t115\pt` (Windows 11, Python 3.10).

- **First full run:** 89 failed, 4448 passed, 21 skipped, 3 xfailed, 9 errors, 3524.6 s.
- **Isolated rerun of the 98 failed/errored ids** with a short basetemp (`D:\archeus-t115\.pt`): **98 passed**, 255.8 s.
- **So no failure reproduces.** All 98 were caused by the environment:
  - **Port reuse, `WinError 10048`** (about 85 of them). Five other forks were running suites on this machine
    at the same time. This hit test_api_*, test_graph_routes, the TUI acceptance tests, the e2e tests and the
    judge `[http]` tests.
  - **Basetemp path too long**: 44 in `test_repo_store.py` failed with "git fetch failed: cannot lock ref
    'refs/archeus/incoming/exec/<id>/seed': unable to create directory". The scratchpad basetemp is about 100
    characters, and the archeus home plus the store path inside it ran past the Windows path limit.
  - **Throughput under load**: `test_writer_throughput` measured 307 commands/s against a floor of 500.
  - **Basetemp contents**: `test_spa_copy` found "hash" segments in the page, and they were the session-id
    segments of the scratchpad basetemp path.
- **Net result for c8f5bd5 on this Windows machine:** 4546 passed, 0 failed, 21 skipped, 3 xfailed. These are
  two runs, not one clean full run.
- **CI run 39246792936 failures are not reproduced locally.** The 3× `test_execution_units`
  unresolvable-path failures and `test_s10b_loop_guard[http]` both passed here. The Linux/macOS repo-store hook
  failures cannot run on Windows. All of them belong to T-122.

### xfail (3), all strict, none is `phase:P20`
- `tests/v1/contract/test_adapter_contract.py::test_the_codex_adapter_normalises_a_recorded_stream`: phase:P23 (the Codex adapter, moved there by p20 D9)
- `tests/v1/judge/test_g08_legacy_import.py::test_importing_a_legacy_home_twice_yields_the_same_world[inprocess]`: phase:P22
- the same test `[http]`: phase:P22

### skip (21)
- `test_pv20_isolation_windows.py:36` (1): real OS boundary tests run only with ARCHEUS_REAL_BOUNDARY=1. **This bears on G6.**
- `test_core_client.py:57` (2): got empty parameter set for (op)
- `test_claude_code_live.py:39,50` (2): the real Claude Code run is opt-in (D15 / ADR-0021)
- `test_core_lifecycle.py:173` (1): POSIX file modes
- `test_long_paths.py:53` (4): pytest basetemp too long for a 109-character worktree root. These are environment skips. They were not rerun with the short basetemp.
- `test_repo_store.py:427` (2) and `test_pv20_runtime_stage.py:297` (1): this account cannot create a symlink (WinError 1314)
- `judge/support.py:380,414,423,431` (8): paired clients, device tokens, SPA and TUI exist only over the http binding (the in-process twin of `[http]` tests)

## 2. Client and generators
- `npm ci --offline`: OK (26 packages).
- `tsc --noEmit`: **pass**.
- `npm run build`: **pass**. The SPA was built into archeus/api/static.
- `npm test` (node --test): **244/245 pass, 1 fail**. The failure is `the rows read the page's reduced motion and its slow frames` (test/rowpulse.test.ts:184). The test matches `/reduced: reducedMotion,\n\s+degraded/` against ui.tsx as read from disk. This checkout has `core.autocrlf=true`, so the file is CRLF (`i/lf w/crlf`) and the regex misses. The test assumes LF line endings, and the product is not at fault. CI Linux is LF and passes.
- `py tools/gen_ui.py --check`: **pass** ("current and every state has a presentation").
- `py tools/gen_api_docs.py --check`: **pass**.
- `npm audit --offline --audit-level=high`: printed "found 0 vulnerabilities", exit 0. **Treat this as NOT RUN in substance.** An offline audit has no advisory data, so it cannot report findings. The real audit is CI's `npm audit --audit-level=high` in the v1-client job.

## 3. Mutation suites (`ARCHEUS_E2E=1 py tools/mutate_<x>.py`) — PARTIAL

| Suite | Result |
|---|---|
| mutate_ap1 | 28/28 killed |
| mutate_p8 | 22/22 killed |
| mutate_p9 | 35/36 killed. **SURVIVED: M25** "at most one live approval per identity (index dropped)". **Confirmed** by an isolated rerun at 18:24 (`mutate_p9.py M25`: 0/1 killed, 12 s), so this is real and not load |
| mutate_p10 | 37/37 killed |
| mutate_p11 | 36/36 killed (the loop was stopped at the owner's stop, after p11 had finished; the tree was checked clean afterwards) |
| mutate_p12, p13, p14, p15, p16, p17, p18, p19, p19_5, p20, p21 | **NOT RUN** (owner stop) |

159 of about 996 mutants were run (158 killed, 1 survived). About 837 were not run. That includes every P20 Q-mutant (mutate_p20, 132) and the P19/P19.5 suites that §10 wants re-run.

## 4. p20-design-gate.md §10, bullet by bullet

| §10 bullet | Status | Evidence |
|---|---|---|
| G5 and G6 pass with ADR-0049, ADR-0051 §2 and ADR-0052 §6's tests | **NOT MET** | G5 (2 tests) and the existing G6 tests pass. ADR-0051 §2's boundary tests do not exist: slice G is PAUSED (gate §12 items 92–97). G1 and G2 stay **Critical and open** (gate line 2920; pv20 design §7, line 813; ADR-0053 line 418). The real-boundary PV-20 tests skip without ARCHEUS_REAL_BOUNDARY=1, and T-111 (E1 evidence) is BLOCKED |
| No `phase:P20` xfail left (G7's passes or re-marked by D9) | **MET** | The only xfails are phase:P23 (1) and phase:P22 (2) |
| Every Q-mutant killed; affected P19 mutants re-run | **NOT RUN** | mutate_p20, p19 and p19_5 were not run (owner stop). One confirmed survivor in the P9 suite (M25) |
| Full tests/v1 with E2E; client type check, unit tests, gen_ui --check, gen_api_docs --check; traceability and design gates | **MET with caveats (PARTIAL)** | 0 real failures: 4448 pass in run 1, and the 98 environment failures pass on the isolated rerun. tsc, gen_ui and gen_api_docs pass, and the judge traceability and design gates are inside tests/v1. Node is 244/245, with the one failure being the CRLF test assumption. CI on c8f5bd5 is red (T-122) |
| Threat model, secrets review, remote-access review, dependency audit committed, no High open | **NOT MET** | Slice I's secrets review, remote-access review and dependency audit are committed (gate §12 slice I, items 109–113, with corrections at 2588 and in T-096). The threat model is slice G's (ADR-0051 §3), and slice G is paused. Two **Critical** findings (G1, G2) are open, so "no High open" cannot hold |
| Manual checks A-M1, B-M1, B-M2, F6-M1, C-M1, C-M2 (owed by the user) | **NOT RUN** | All six are marked NOT RUN in the §10 table. They are the user's to perform |
| Observed runs (D15) | **NOT RUN** | §14.E: the observed run through Core is still NOT RUN, gated by ADR-0021 (`archeus terms claude_code permit` is the user's act) |

**Conclusion:** P20 is not complete at c8f5bd5. The blockers are G1 and G2 (Critical; PV-20 is not verified),
slice G, the full mutation pass, the manual checks, D15 and the red CI.

## 5. Proposed cards (one line each)
- **T-115a** P9 M25 survives (confirmed when run alone). Add the test that catches a dropped one-live-approval-per-identity index.
- **T-115b** Finish the mutation pass: p12–p21, with **mutate_p20 (Q01–Q132) and p19/p19_5 first**. Run on an idle machine; the suites edit the sources, so one checkout per run.
- **T-115c** Make `rowpulse.test.ts:184` CRLF-tolerant. Either normalise `\r\n` before matching, or pin `clients/app/src/**` to `eol=lf` in .gitattributes. Today it fails on every Windows `autocrlf=true` checkout.
- **T-115d** Repo store on a long home path: git ref locks fail once home + `repos/.../refs/archeus/incoming/exec/<26-char id>/seed` passes MAX_PATH. Check whether a real user home this long is reachable (`test_long_paths` covers it but skipped here), and whether the store should use `core.longpaths` or refuse up front with a clear message.
- **T-115e** Make the test suite robust to concurrent runs on one machine: about 85 failures were `WinError 10048` port collisions. Either bind port 0 everywhere and read the port back, or document that one suite runs per machine.
- **T-115f** A real `npm audit` with network as part of K. The offline audit gives no evidence.
- Already carded elsewhere: CI red on c8f5bd5 → **T-122**; G1/G2 → PV-20 / slice G; T-111 BLOCKED (needs real OS isolation).

## 6. Not run
mutate_p12 through p21 (including all of P20's Q-mutants and the P19/P19.5 re-runs), a real npm audit,
`test_long_paths` (skipped because the basetemp is too long), the real-boundary PV-20 tests
(ARCHEUS_REAL_BOUNDARY=1), symlink-dependent tests (no symlink privilege), the D15 observed run and all six manual
checks.

Artifacts are in the scratchpad: `...\scratchpad\t115\v1.log`, `v1.xml`, `rerun.log`, `mut_*.log`. Two stray
files were also left: `D:\archeus-t115-build.log` and `D:\archeus-t115-node.log` (build and node test output).
