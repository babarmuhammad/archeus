# T-043 · K4: no Core Git in the facts of a known-isolated execution — contract

Claude (fork), 2026-10-13. Read-only, at `pv20-s2` `a16d3c9` (worktree `D:\archeus-pv20-s2-l`). No tests, no Git in any workdir, no content scan, no native call. Lines cite the current tree; T-030's tables cite an older one (`manager.py:460/462/568/571` there are `:483/485/591/594` here).

T-030 K4 (`T-030-seed-import-contract.md`, K-table) derives facts from the import and so waits for K3. This note splits out an **interim K4a** that needs nothing from K1-K3: zero Core Git for known-isolated executions now, with the missing facts stated rather than faked. The record-derived facts (K4b) stay T-030's.

T-042 (K5a, in progress in parallel) owns the verification worker's Git; it is cited here only as a dependency (§1 rows F6-F7) and nothing below edits its files.

## 1. Every Core Git read of an execution's workdir

Known-isolated (K) = the execution has an isolation record, or its row says `isolated is True` (the T-038 fallback). Legacy None is the row prepared before T-036, which N1 routes as ordinary.

| # | Site | Git | Reached for K today? | Legacy None |
|---|---|---|---|---|
| F1 | `manager._workspace` `:379` `git_branch(root)`, `:389` `branch_exists`, `:390` `add_worktree` | in the project **root**, not a workdir | No. No-project returns at `:359-364` before any Git; a K project execution raises at `:365-371`, "before any git probe of the root" (A1/T-027) | Ordinary: yes |
| F2 | `manager._hooks` `:483` `git_branch(workdir)` | `rev-parse --abbrev-ref HEAD` (`local.py:284-289`) | No, **incidentally**: gated on `e.branch`, and no K execution has a branch while F1 refuses projects | Ordinary when it has a branch |
| F3 | `manager._hooks` `:485` `git_remotes(workdir)` | `remote -v` (`local.py:292-302`) | No, same incidental gate | Same |
| F4 | `manager._facts` `:591` `diff_stat(workdir)` | `diff --stat HEAD` (`local.py:315-321`) | **Yes.** Gated on `e.branch or e.workdir`; a no-project K execution has `e.workdir = ExecPaths(e.id).work`. Runs at every live end: `_watch` `:409` → `_collect` `:551`, which calls `_facts` **before** it computes `isolated` (`:564`) | Yes |
| F5 | `manager._facts` `:594` `end_state(workdir)` | `rev-parse`, `diff --binary HEAD`, `ls-files --others`, `hash-object --stdin-paths` (`local.py:324-352`) | **Yes**, same path | Yes |
| F6 | `worker._workspace_of` `:172-183`; `_run_and_record` `:216-217`; `_retry` `:258`; mission `:317`, `:323`, `:350` | `git_head`, `git_dirty`, `git_snapshot` (`add -A`, commit), `merge_base` | Yes (T-041 M1). **T-042's scope** ("no workdir Git for True") | G1: kept (owner) |
| F7 | `worker._merge` `:282-289` | merge of an execution-claimed revision into the integration worktree | T-042's merge filter | G1 |

Not Git, and unchanged by this card: the restart path for K (`_reconcile_one` `:718-719` → `_reconcile_isolated`, which passes `facts={}` at `:826`/`:831` and never calls `_facts`); stream facts (`_facts_from` `:913-924`, `_progress` `:459-465`: data read from the stream, redacted, clipped); checkpoints and continuations (database only, `checkpoint.py`, `manager.py:322-334`); the canonicaliser's `_git` (`canonical.py:162-199` classifies an argv, runs nothing).

**Why F4/F5 are an escape (A5).**
- **Unpinned Git.** `proc.run` (`claude_sessions/proc.py:47-73`) runs Git with Core's whole environment and no pinned configuration, with `cwd` set to the workdir. Git discovers a repository from there upward.
- **The execution controls the repository.** The workdir is the execution's own and writable by it, so a `.git` it plants is the repository Core's Git uses. That `.git` can be a directory with its own config, or a gitfile pointing elsewhere.
- **Programs Core may run.** Per Git's documented behaviour, `diff --binary HEAD` and `hash-object --stdin-paths` (no `--no-filters`) apply clean filters named by `.gitattributes`. An index refresh can start `core.fsmonitor`.
- **What `--no-optional-locks` (`local.py:336`) stops.** It stops index writes, not configured programs.

This was not executed here. It is dormant while `PRODUCTION_DISPATCH_ENABLED` is False (`isolation.py:80`) and no grant is applied.

**A data point, not an escape.** `diff --stat` lines name files the execution chose. They reach the next continuation's prompt through the checkpoint (`manager.py:322-334`), redacted and clipped (`checkpoint.py:55-56`). That is data, as `_facts_from` already is.

## 2. Deciding K without a new authority

- **Live end (`_collect`).** The value `isolated` at `:564` is `_isolated(e, record)`: True on a record or on `e.isolated is True`, False otherwise (`:762-776`). It is exactly K. It only has to be computed before `_facts`. Its None branch (a registry note, then False) is the legacy rule of §5 Q1, not K.
- **Hook request (`_hooks`).** A process answering hooks was spawned by this Core: an isolated process is never re-adopted (`_reconcile_isolated` `:809-813` kills it). Since T-036, every preparation records a bool decision (`executions.py:104`). So `e.isolated is True` is exact for a live hook, and no record read is needed per request.
- **Restart (`_reconcile_isolated`).** Reached only for K (`:718`).

## 3. Interim K4a: zero Core Git for K, unavailable facts stated

Changes, all in `archeus/core/execution/manager.py`:

1. **`_collect`.** Move `isolated = self._isolated(e, self._isolation_record(e.id))` (`:564`) above `facts = self._facts(e, p)` (`:551`) and pass it: `self._facts(e, p, isolated)`. The variable is otherwise used unchanged.
2. **`_facts(e, p, isolated)`.** For K, return without any node call:
   - `files_changed`: a single line, `'(not measured: an isolated execution; Core runs no Git in its workdir)'`.
   - `end_state`: None.
   - `decisions` and `last_error`: as today.

   Ordinary and legacy None: unchanged.
3. **`_reconcile_isolated`.** At `:826` and `:831`, replace `facts={}` with the same not-measured `files_changed` line and `end_state` None. Today `{}` renders the checkpoint's "Files changed" as `- (none)` (`render.py:26-27, 41`): a fake empty.
4. **`_hooks`.** Make the guard structural rather than incidental:
   - `known = e.isolated is True`.
   - `branch_now` and `remotes` are read only when `e.branch and not known` (otherwise None and `{}`).
   - `branch_ok = e.branch is None or (not known and branch_now == e.branch)`.

   A K execution with a branch cannot exist today (F1). If one did, it would be halted, failing closed, by the existing `branch_ok` refusal (`executions.py:643-644`), whose text ("HEAD is not branch") is then inaccurate. T-030 row 4/Q7 replaces this with the Core-recorded branch once seeded workspaces exist (K4b).

Why a line in `files_changed`, and not a new field:
- The field is already free text: `diff --stat` emits a summary line beside the per-file ones.
- No schema or `checkpoint.py` change is needed.
- `render.py` then shows the statement under "Files changed" instead of "(none)".

One consumer counts lines: `live.py:110-112` prints `%d file change(s)` and would say 1. It already over-counts every ordinary checkpoint by the stat summary line, so its semantics are "stat lines". A follow-up may exclude the not-measured line; this card leaves it.

Not touched: `node/local.py`, `executions.py`, `checkpoint.py`, `render.py`, and the T-042 files.

## 4. Effects

- **`end_state_digest`.** None for every K end. Today it is also None unless the execution made a repository in its workdir, in which case it is a digest computed by Git under the execution's own configuration. Its only reader is `no_progress` (`executions.py:515-541`), and only for a **pressure continuation that hands off again** (`stop_reason == 'pressure'` and `handoff_from` set). Unmeasured is no progress (`pressure.py:104-112`), so the second link is charged with no continuation and the task takes `charged_failure` (`executions.py:559-578`), reason "its end state could not be measured" (wording unchanged). A first hand-off is unaffected. Owner Q2.
  - **No-project chains are weak anyway.** A no-project continuation is prepared in a **fresh** `ExecPaths(new id).work` (`_workspace` `:359-364`), so its digest never compared the same directory. This is recorded, not changed.
- **`files_changed` / checkpoint.** The statement replaces Git's stat. A checkpoint decides nothing (`checkpoint.py:7-10`); it is history, the prompt suffix of a continuation (`manager.py:322-334`) and `live.py`'s summary.
- **Hand-off progress** (`record_progress`, offsets, usage, context, pressure): no Git, unchanged. The A7/H2 end routing at `:564-586` is unchanged; only `isolated`'s position moves.
- **Retries.** A fresh attempt reads neither the checkpoint nor the digest (the only readers are `manager.py:327` for `handoff_from` and `live.py:108`). Charging is unchanged except in the Q2 case.
- **Hooks.** No behaviour change today; the gate becomes explicit.
- **Verification** (depends on T-042). Until T-042 lands, `worker.py:174` still runs `git_head` in the same workdir after the end. K4a closes F4/F5 and T-042 closes F6/F7, so A5 for no-project K needs both. The two can land in either order: their files are disjoint.

## 5. Three tiers of facts, kept separate

- **R: Core's records (K4a, now).** The decision, workdir path, process sequence, observed exit, stream-derived decisions and last error, and hook events. Nothing is read from the workdir.
- **W: a bounded, data-only walk of `ExecPaths.work` (later, no-project only).** A Core-computed digest and file list, with no Git, never executed. It is not proposed now, because two preconditions are open:
  - **Writer quiescence confirmed.** The held-Job count fence (T-030 second correction, C6) must say no descendant can still write. A walk before that reads a moving tree.
  - **A link and race policy** (T-030 §3.3 Q1/Q3): non-following `lstat`, refuse reparse points and multiply-linked files, as `staging.py` does, plus bounds on count, bytes and depth.

  It would give no-project K executions back a progress digest.
- **I: the canonical import diff (T-030 K3/K4b, project only).** The digest is the tree id of `import_revision`, and the stat is `diff --stat seed import` in the Core store, run by the pinned runner (T-030 rows 6-7). It does not exist for no-project executions.

## 6. Owner questions

**Q1. Lifecycle Git for legacy None.** F4/F5 for a row prepared before T-036 and still running at upgrade. A6's G1 covers verification only and is not read as answering this.
- **L1 (recommended).** Keep Git for None. It matches N1 (lifecycle routing ordinary) and G1. Moreover, while G1 stands the verification worker runs Git, including `add -A` and commit, in the same workdir right after the end, so withholding the cheaper read at the end protects nothing by itself. The population is bounded (`isolated` None, `process_seq >= 1`, not ended at upgrade) and already noted in the registry as `isolation_decision_unknown` (`:774-775`).
  - Production isolated dispatch has never been enabled, so such a row is expected to be ordinary. That is not provable from the row.
- **L2.** None counts as unmeasured: no Git, and the same statement. This is meaningful only if G1 is also revisited.

**Q2. Isolated pressure chains.** With the end state unmeasured, a K pressure continuation that hands off again always stops, charged (§4).
- **P1 (recommended).** Accept until tier W or I gives a digest. ADR-0047 fails closed.
- **P2.** Exempt K from `no_progress`. This relaxes the guard: a looping chain would continue until its attempts run out.

## 7. Card manifest (K4a)

- **Files:**
  - `archeus/core/execution/manager.py`: `_collect`, `_facts`, `_hooks`, `_reconcile_isolated` only.
  - `tests/v1/unit/test_pv20_isolation.py`: its `_collect` rig stubs `m._facts = lambda e, p: {}` (`:953`) and must take the new argument; new trace tests go here.
  - `tests/v1/unit/test_execution_units.py`: hook rig controls.
- **Depends on:** nothing. It is disjoint from T-042 (`application/verification.py`, `verification/worker.py`, `test_verification*`). It shares `manager.py` with T-030 K2/K3/K6, so it goes before them or one at a time.

**Fake-trace tests.** A `FakeNode` subclass whose `git_branch`, `git_remotes`, `diff_stat`, `end_state`, `git_head`, `git_dirty`, `git_snapshot`, `branch_exists` and `add_worktree` each raise `AssertionError` (a sentinel). No real Git, process or native call.

1. **Live end, record present.** For K ending OK, ERROR, killed, HANDING_OFF with exit 0 (→ `record_handoff`), HANDING_OFF otherwise, and PAUSING: no sentinel fires, and the `facts` passed carry the not-measured line and `end_state` None. The A7 routes are as in `TestIsolatedLiveEndRoute`.
2. **T-038 fallback.** Record missing and `e.isolated is True`: same as 1.
3. **Restart.** `_reconcile_isolated` for PAUSING, STOPPING and HANDING_OFF passes the not-measured facts, never `{}`.
4. **Hooks.**
   - `e.isolated is True` and branch None: the request is answered, with `ctx` `branch` None and `remotes` `{}`, and no sentinel fires.
   - Forged `e.isolated is True` with a branch: answered `halt`, and no sentinel fires.
5. **Controls.** Ordinary (`False`) and legacy None (under L1) call `diff_stat` and `end_state` once each at the end, and the hook Git when a branch is set, as today.
6. **Rendering.** `render.checkpoint` of a Checkpoint built from the K facts shows the statement under "Files changed", never `- (none)`.

**Mutants, each to be caught:**
- `_facts` ignores `isolated`.
- `isolated` computed after `_facts`.
- The fallback (field True, record missing) not treated as K.
- The `_hooks` gate removed.
- `_reconcile_isolated` keeps `{}`.
- The statement replaced by `[]`.

**Verify:** from the S2 root, `py -m pytest -m "not real_process" tests/v1/unit/test_pv20_isolation.py tests/v1/unit/test_execution_units.py tests/v1/integration/test_execution.py tests/v1/integration/test_context_capacity.py tests/v1/unit/test_mutation_suites_parse.py -q`. The stage/install guard stays active.

**Not claimed:** A5 confinement, that Git honours the hazards above here (documented behaviour, not executed), quiescence, a link policy, or anything about F6/F7 before T-042.
