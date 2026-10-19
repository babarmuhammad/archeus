# T-041 · A6: command-verification authority and interim guard contract

Card T-041 (analysis only). Claude (fork), 2026-10-13, read-only. Every `file:line` is at the S2 worktree's stable baseline `d2ecac4`, read with `git -C D:/archeus-pv20-s2-l show d2ecac4:<path>`. That baseline already holds `Execution.isolated` (T-036, `cea27bb`; field at `entities.py:1014`, check at `:1020-1021`) and the lifecycle fallback (T-038, `dc7c437`/`648d039`). T-040's runtime-stage wiring is pending in the same worktree and touches `manager._spawn`/hook settings and `isolation.default_plan` only; no path in this note crosses it ("pending T-040" where it would).

Refs: T-030 §2 C9, §6 rows 8-25, Correction C-1012-T030 §2 (A6 guard, `Mission.isolated_output`) and §3.3 Q2-Q4; T-035 §5 (readers); T-037 §8 (three different things); T-038 notes (owner's N1); PV-20 §3.9 (R4b, fail-closed); A5 (pinned Git, no Core Git in an execution workdir).

## 0. What this note does and does not do

- It maps every verification, retry, merge and review path, and every Git read over execution-derived paths, at `d2ecac4`, including what runs **before** any command check (§2).
- It pins who may authorise an unconfined command check and from which durable fact (§3), separates four kinds of thing (§1), states the invariants that keep a skipped check or a missing canonical revision from ever becoming PASSED (§5), and gives mission provenance a monotonic definition (§6).
- It proposes one small implementation card now (K5a) and places the rest behind T-030's K1/K3 and owner questions (§7).
- It implements nothing, runs no test, command or Git operation, and makes no confinement claim. It does **not** adopt T-030 §3.3 Q4 (whether activation waits for A6 or goes through a human). K5a's routing to a human is fail-closed behaviour of a dormant path, not an activation policy.

## 1. Four different things

| | What it is | What it may decide | Where today |
|---|---|---|---|
| **Command guard (A6)** | Whether Core may run a project's test/build/criterion commands unconfined, as the user, over content an execution produced | Only whether a CodeVerifier starts. Never a verdict by itself | No guard exists. `run_commands` → `node.run_check` (`evidence.py:65-91`, `local.py:490-524`) with Core's whole environment (`local.py:499`) |
| **Core Git rule (A5)** | Whether Core may run Git *inside* an execution's workdir, and under which configuration Git runs over execution-derived content anywhere | Which revision is canonical; whether a diff/merge may run | No pin: `proc.git` passes nothing (`claude_sessions/proc.py:76-81`). Core Git runs in every workdir (§2) |
| **Data-only evidence** | Facts Core derives without executing anything the execution chose: routed vs reported model from the Core-captured stream (`evidence.py:111-143`), and, once K1/K3 exist, a diff computed between two Core records in the store | Corroboration only. `verdict_of` never passes without a command check (`verification.py:47-59`, `:57-58`) | `changes_check` (`evidence.py:94-108`) is a Git diff in the user's root of an execution-claimed head: not data-only today |
| **Human disposition** | A GenericVerifier row AWAITING_HUMAN, decided only by a user device (`verification.py:339-371`, `:342-343`) | PASSED/FAILED of that row. It never supplies a revision | `start(verifier='generic_human')` (`verification.py:172-177`) |

The four do not substitute for one another: a human PASSED is not a code PASSED, a data-only check cannot pass a battery, and a pinned Git diff authorises no command.

## 2. Every path, at `d2ecac4`

"Before check" marks operations that run before any command check could be guarded at `run_commands`.

| # | Where | What runs | Over | Before check |
|---|---|---|---|---|
| V1 | `worker.py:174` `git_head(workspace)` (`local.py:394-399`) | `git rev-parse` | the execution's workdir | yes |
| V2 | `worker.py:177` `git_dirty(workspace)` (`local.py:407-412`), task-branch executions | `git status --porcelain` | workdir | yes |
| V3 | `worker.py:178` `git_snapshot` (`local.py:415-426`) | `git add -A`, then `commit --no-verify` | workdir | yes |
| V4 | `worker.py:181-183` `branch_exists(root)`, `git_merge_base(root, head, against)` | Git in the user's root, on the execution-claimed head | user root | yes |
| V5 | `worker.py:196-202` the human path | records V1/V3's head as the row's `revision`, and the workdir as `workspace` | — | yes: it runs *after* V1-V4 |
| V6 | `worker.py:212-213` → `evidence.py:100` `git_numstat(root, base, revision)` | `git diff --numstat` | user root, execution-derived commits | no (it is a check) |
| V7 | `worker.py:214` → `evidence.py:77` `run_check(ws)` | the project's commands | workdir | the check |
| V8 | `worker.py:216-217` `git_head`, `git_dirty(tracked_only)` | Git | workdir | after |
| V9 | `worker.py:242-249` task retry | V6-V8 again on `v.workspace` | the recorded workdir | the check |
| V10 | `worker.py:250-260` mission retry | `run_check` on `v.workspace`, then `git_head` | mission worktree | the check |
| V11 | `worker.py:315-321` `git_head(_mission_wt)` | stale-head detection | Core's mission worktree | yes |
| V12 | `worker.py:323` | when nothing was integrated, the mission workspace is **the user's project root** | user root | yes |
| V13 | `worker.py:342-353` mission criteria | `run_check` on `ws`, then `git_head` | mission worktree or root (V12) | the check |
| V14 | `worker.py:269-299` `_merge` | `git_merge_base` (`:282`), `mission_worktree` (`:283`, `local.py:456-468`), `git_head`/`git_is_ancestor` (`:285-286`), `git_merge` (`:289`, `local.py:471-487`), `remove_worktree` (`:295`) | user repository, mission worktree, the task's worktree | after a PASSED |
| V15 | `worker.py:363-364` `_review` | `git_numstat(root, integration_base, integration_head)` | user root, merged output | after mission verification |
| M1 | `manager.py:470-472` hook context | `git_branch`, `git_remotes` | workdir, when `e.branch` is set | during the run |
| M2 | `manager.py:575-581` `_facts` | `diff --stat HEAD`, `rev-parse`, `diff --binary HEAD`, `ls-files --others`, `hash-object --stdin-paths` (`local.py:315-352`) | **every** workdir with `e.workdir` set, isolated no-project ones included | at the end |
| S1 | `engine.py:237-242` → `work.py:408-425` `record_task_verification` | a PASSED with no `start`, no `execution_id`, no revision | — | — |

Notes on the map:
- **What V1-V3 run is chosen by the workdir.** V2 and V3 read the workdir's own repository configuration; `git status` and `git add` can invoke an `fsmonitor` command and clean filters named there or in in-tree attributes, and `--no-verify` skips only the pre-commit and commit-msg hooks, not post-commit [UNVERIFIED in this repository; standard Git behaviour]. So for an isolated workdir, a guard placed at `run_commands` comes too late: the execution's programs can already have run as the user at V2/V3. **The guard must decide before `_workspace_of` (`worker.py:169-184`) is called.**
- **M2 is the same hazard outside verification.** For an isolated no-project execution (`manager.py:346-351`, `e.workdir = ExecPaths(e.id).work`), `_facts` runs `diff`/`hash-object` in its workdir at every end. That is an escape from isolation, not a verification fault. It is T-030 K4's (Correction C-1012-T030 §2), dormant while dispatch is off; restated here because it outranks A6.
- **S1 is a second writer of PASSED** that bypasses `V.start`/`V.record`. Production never wires it: `Ports.verifier` defaults to None (`runtime.py:112`), and then the VerifyWorker verifies (`runtime.py:472-477`). It is the injected stub (`ports.py:163-173`).
- No other module runs commands or Git over execution paths: `reviewer.py` only reads rows (`:41-91`), and the review call's workdir is `ARCHEUS_HOME` (`worker.py:370`).

## 3. Authority, pinned

Two predicates, deliberately different.

**A6, the command guard (one predicate, mission-wide):**

> A command check may run unconfined only when **every prepared execution of the mission** (`process_seq ≥ 1`, any task, any plan version, any attempt) has `isolated` **exactly `False`**.

- `True` → guarded. `None` (legacy, or a `work.record_spawn` test row) → guarded. A missing execution row cannot occur for a prepared one; a task with no verified execution never reaches a check.
- **Mission-wide on purpose.** Content moves between executions of one mission four ways: a worktree task starts from the mission branch once something merged (`manager.py:375-377`); a retry or hand-off reuses the per-task worktree today (`manager.py:372`, `local.py` `add_worktree` returns early when the directory exists) and, under T-030's defaults, is seeded from the predecessor's import; mission criteria run on the merged branch. Tracking each flow precisely needs lineage fields; the mission closure needs none and is never wrong in the unsafe direction. Its cost is over-approximation (§8).
- **No-project executions** are under it unchanged. That their command list is empty today (`evidence.py:27-28`) is not relied on.
- **No import never means unconfined.** The predicate reads provenance only, never whether a revision or workspace exists.
- **Mixed missions** are guarded as a whole, task checks and mission criteria alike.

**A5, Core Git in a workdir (per execution):**

> Core runs Git in an execution's workdir only when that execution's own `isolated` is exactly `False` (or `None`, per owner Q1), and never for `True`.

For a `True` execution the worker reads no revision from the workdir: `revision` and `base_revision` are None until T-030's K3 supplies `import_revision`, and V1-V4 are not called. An ordinary execution in a guarded mission keeps today's Git reads of its own linked worktree (they are the user's repository, pinned later by K1/K5b); only its commands go to a human.

### Matrix

| Execution `isolated` | Mission (A6 predicate) | Project | Core Git in its workdir (V1-V4, V8) | Command checks (V7, V9, V10, V13) | Verification |
|---|---|---|---|---|---|
| False | all False | yes | as today | as today | CodeVerifier as today |
| False | some not False (mixed) | yes | as today | **none** | human, revision as read |
| True | (guarded by it) | yes | **none** | none | human, revision None until K3. Unreachable today: T-027 refuses isolated project executions (`manager.py:352-359`) |
| True | (guarded) | no | **none** | none (and empty today) | human, revision None |
| None | (guarded by it) | yes/no | Q1: as today (G1) or none (G2) | none | human |
| any, no import | — | — | as per the row's `isolated` | none unless the whole mission is exactly False | as above; a missing import never selects the unconfined path |

### Where the owner's N1 would leak if reused for verification

N1 (T-038) keeps a legacy `None` execution on the *ordinary lifecycle route* (`manager._isolated`, routing to adoption and ordinary end rules). If verification read the same predicate ("isolated when the record exists or the field is True"), every `None` execution would be treated as ordinary and its commands would run unconfined at V7 (`worker.py:214`), V9 (`:249`), V10 (`:256`) and, through the mission, V13 (`:347`); the transient record is gone after teardown anyway (`isolation.py:943-947`), so that predicate collapses to `e.isolated is True` for every ended execution. **Verification must therefore never import or reuse `manager._isolated`;** its predicate is "exactly False", a separate function in `application/verification.py`.

## 4. Ordering and the one sink

Every command run is preceded by a write transaction the worker cannot skip: `V.start` (`worker.py:203` before `:207`; `:343` before `:347`) or `V.retry` (`worker.py:241` before `:249`/`:256`). So the guard is enforced twice with one implementation:

1. **Worker (read):** evaluated before `_workspace_of`, to choose the path and to skip V1-V4 for a `True` execution.
2. **Sink (write):** `V.start` refuses `verifier='code'` for a guarded subject, and `V.retry` sends a guarded row ERROR → PENDING → AWAITING_HUMAN (`generic_verifier`, an existing edge, `states.py:237`, `:240`) with `_hold`, instead of `start`.

The two can disagree only in a race where the mission becomes guarded between the read and the write. The predicate is monotonic (§6), so the sink's refusal is a lost race (`pass_once` catches `V.Refused`, `worker.py:92-94`) and the next pass reads the guarded state. Nothing is persisted on that path, so nothing needs rollback.

## 5. No false PASSED

- **A skipped command check is never PASSED.** Guarded subjects never start a CodeVerifier, and `verdict_of` already turns a battery without a command check into ERROR (`verification.py:57-58`). The guarded row is AWAITING_HUMAN with a reason that says the checks were withheld (A6), not "nothing deterministic can decide this" (`verification.py:174`).
- **A legacy CodeVerifier row of a guarded execution is never re-run.** Rows created before K5a (or before T-036) can be ERROR and due a retry (`worker.py:133-136`); `V.retry` routes them to a human (§4). The boot sweep's RUNNING → ERROR (`verification.py:394-406`) feeds the same route.
- **A missing canonical revision is never merged.** For a `True` execution `revision` stays None; `begin_merge`'s guard needs a PASSED row with a non-None revision equal to the one merged (`guards.py:359-370`). Today a human-PASSED row with revision None and a task-branch execution would sit in `integration_state = PENDING` (`verification.py:256-257`) and fail that guard on every pass as a lost race (`errors.py` `LOST_RACE`): stuck, not merged. What such a task becomes is T-030 §3.3 Q2 (no import), unchanged; unreachable while T-027 holds.
- **A human PASSED never carries an execution's claim as canonical.** Today V5 records the workdir HEAD as `revision` and a human accept makes it mergeable (`settle_task` → `_merge`). For a `True` execution K5a records None instead; the canonical revision comes only from K3's import.
- **No root fallback for a guarded mission.** V12 runs mission criteria in the user's project root when nothing was integrated; for a mission whose isolated output never merged, criteria would pass on code that does not contain the work. A guarded mission's criteria are all human, and its rows record no root workspace.
- **S1** stays a test port. If production ever wires a verifier port, it needs the same sink check; K5a adds a static test that `Ports.verifier` is None in the production runtime construction.

## 6. Mission provenance: derived, not stored

T-030's Correction §2 proposed a sticky `Mission.isolated_output` set in `settle_task`'s transaction. Now that `Execution.isolated` exists and is write-once, the same fact is a pure read:

> `guarded(mission) = any(e.isolated is not False for e in executions where e.mission_id == mission.id and e.process_seq >= 1)`

(`executions.mission_id` is a promoted column, `migrations/0002_work.sql:44`; `process_seq` is in the body, filtered in Python.)

- **When it is "set":** in the transaction that first prepares an execution of the mission with `isolated` not exactly False, i.e. T-036's `prepare_process` (`executions.py:95-139`). A refused preparation writes neither the field nor `process_seq`, so it does not count.
- **Monotonic by construction, never clears:** executions are never deleted; `isolated` is written once and never relabelled (T-036); `process_seq` only grows. A legacy mission holding a `None` execution is guarded from the upgrade on.
- **No transaction or rollback rules of its own:** nothing is written, so nothing can be half-written; the worker and the sink each re-derive it (§4).
- **Why not the sticky field:** it would need a writer in `settle_task`, a default for legacy missions (three creation sites: `commands.py:79`, `conversation.py:658`, `authorization.py:1033`) and a lineage rule for seeds and retries. The derivation covers all three with no field. If the over-approximation (§8) later costs too much human time, a field with precise lineage can be added then.

## 7. Cards

### K5a · A6 interim command guard (implementable now; no owner question blocks it beyond Q1)

| File | Change |
|---|---|
| `archeus/core/application/verification.py` | `unconfined(conn, mission_id)`: the §6 predicate, the only implementation. `start`: refuse `verifier='code'` when not `unconfined`; a guarded `generic_human` start uses the A6 reason text. `retry`: for a guarded subject fire `retry` then `generic_verifier` and `_hold`, never `start` |
| `archeus/core/verification/worker.py` | `_verify_task`: before `_workspace_of`, if not `V.unconfined`: for a `True` execution skip `_workspace_of` (revision/base None, no V1-V4), otherwise read as today; start one GenericVerifier row with all criteria (the existing `:196-202` call shape; the Z03 anchor at `:196` stays verbatim). `_retry`: no change needed beyond the sink (`V.retry` no longer returns RUNNING for a guarded row; the worker runs commands only on RUNNING). `_verify_mission`: guarded → every criterion human, no `run_check`, no root fallback (`ws` None when `integration_base` is None). `_review`: guarded → no `git_numstat`, the prompt says the diff was withheld |

No change to `evidence.py`, `local.py`, `manager.py`, entities, migrations, or the engine's stub port. Mutation anchors in `tools/mutate_p13.py` (Z01, Z03, Z13 on `worker.py`; Z02-Z12, Z16 on `verification.py`) stay verbatim; `test_mutation_suites_parse.py` joins the verify set.

**Tests** (fake DB through the existing `core` rig of `tests/v1/integration/test_verification.py`, `isolated` set on executions by direct body update as T-036's legacy test does; a fake node whose `git_head`, `git_dirty`, `git_snapshot`, `branch_exists`, `git_merge_base`, `git_numstat` and `run_check` record and raise):
1. Ordinary execution, ordinary mission: unchanged CodeVerifier path; the node is called as today.
2. `isolated=True`, no project: one AWAITING_HUMAN row, revision None, no node call at all.
3. `isolated=True` with a project (inserted directly, since T-027 refuses dispatch): same, and `settle_task` after a human accept leaves no mergeable revision.
4. `isolated=None`: AWAITING_HUMAN, no `run_check`; Git reads per Q1.
5. Mixed: an ordinary task in a mission holding one prepared `True` execution (another task, even a FAILED attempt): AWAITING_HUMAN, no `run_check`; its own Git reads as today.
6. Mission criteria of a guarded mission: all human, no `run_check`, no root workspace; with `integration_base` None the root is never probed.
7. A pre-existing ERROR CodeVerifier row of a guarded execution: the retry ends AWAITING_HUMAN with `holds_mission`, no `run_check`; a user accept gives PASSED with `decided_by`.
8. Sink: `V.start(verifier='code')` for a guarded task or mission raises `Refused`, nothing written.
9. Race: the mission becomes guarded between the worker's read and `V.start`: lost race logged, no command run, the next pass goes human.
10. Monotonic: a mission stays guarded after the `True` execution ends, its task FAILS, or its plan is superseded.
11. `_review` of a guarded mission: no `git_numstat`; the prompt names the withheld diff.
12. Static: `runtime.Ports.verifier` defaults to None and only test ports set it.

**Mutants**, each to be caught: guard evaluated after `_workspace_of`; predicate `is not True` instead of `is False` (None leaks); predicate filtered by `plan_id` (superseded plans leak); predicate filtered to SUCCEEDED tasks (a failed isolated attempt leaks); predicate ignores `process_seq` (never-prepared rows taint) — expected to be caught by a control test, not to leak; worker skips the guard on the human path's Git reads for `True`; sink check removed from `start`; `retry` guarded path calls `start`; mission root fallback kept for a guarded mission; `_review` still diffs a guarded mission; guarded reason text replaced by the generic one; worker imports `manager._isolated` instead of `V.unconfined`.

**Verify:** `py -m pytest -m "not real_process" tests/v1/integration/test_verification.py tests/v1/unit/test_verification_units.py tests/v1/judge/test_v01_outcome_verification.py tests/v1/unit/test_mutation_suites_parse.py -q`. No new process or native test.

### K5b · canonical revision, data-only `changes`, pinned merge and review (T-030 K5's remainder)

Depends on T-030 K1 (store and pinned runner, C7) and K3 (import), owner T-030 §3.3 Q2 and Q3. It replaces V1-V4 for `True` executions with `e.import_revision`/`seed_revision`, computes `changes` in the store (data-only, may then run for guarded executions), runs V6, V11, V14, V15 under C7, and lifts K5a's "revision None" for `True` executions. Files and tests as T-030 §9 K5. Not authorised here.

### K4 (T-030), restated

M1 and M2 for `True` executions, project or not, from Core records only. M2 is the live escape on the path T-027 permits; K4 should precede any activation, independently of A6.

## 8. Recommended defaults (reversible, not owner questions)

- **Mission-wide closure** (§3, §6), accepting over-approximation: a mission with any `True`/`None` prepared execution routes every command check to a human, including an ordinary task whose worktree never saw the isolated output. Reducing it needs lineage fields; not proposed.
- **Derived provenance, no `Mission.isolated_output` field** (§6). This supersedes T-030 Correction §2's field for the guard's purpose.
- **`changes` is withheld for `True` executions until K5b**: it needs Git on an execution-derived head. Withholding it cannot produce PASSED (`verdict_of`).
- **`_review` withholds the diff for a guarded mission until K5b's pin.** The review still runs; the reviewer is told the diff is missing, not that it is empty.
- **Legacy CodeVerifier rows of guarded executions** go to a human on their next retry, never re-run.
- **S1 (stub port) is not guarded**; a static test pins that production never wires it.
- **Merge (V14) is untouched by K5a.** For a `True` execution there is no revision to merge; for mixed missions the merge's pin is K5b's.

## 9. Owner questions (material only)

1. **Core Git in a legacy `None` execution's workdir (V1-V4).** **G1** (recommended): read it as today; its commands still go to a human. Cost, stated: a `None` row that in fact ran isolated (possible only through Core-authorised test harnesses in development homes before T-036, since production never dispatched an isolated execution) gets Core Git in its workdir, where V2/V3 can run programs that workdir names. **G2**: no Git for `None` either. Cost: every in-flight legacy worktree task loses its recorded revision, and after a human accept its merge sits in PENDING failing the merge guard on every pass (§5) until something else is decided.
2. **Mixed-mission dispatch, needed before T-030 K6, not before K5a.** Once isolated output is merged, an ordinary *execution* dispatched in that mission starts from the mission branch (`manager.py:375-377`) and runs isolated-derived content unconfined as the user. A6 guards only the verification. Allow as today (verification guarded only), refuse ordinary dispatch on a mission holding isolated output, or require such executions to be isolated?

Still open and not re-asked here: T-030 §3.3 Q2 (no import: what the task becomes), Q3 (merge form), Q4 (whether activation waits for A6 or goes through a human). K5a does not answer Q4: it keeps a dormant path fail-closed.

## 10. New findings

1. The guard cannot sit at `run_commands`: V1-V4 run Git in the workdir first, on the human path too, and V2/V3 can execute programs the workdir names (§2).
2. The human path records the execution's own HEAD as `revision` (V5), and a human accept makes it mergeable.
3. Mission criteria fall back to the user's root when nothing was integrated (V12): for unmerged isolated output that is a PASSED that verifies nothing.
4. `_retry` re-runs a CodeVerifier row with no guard; legacy rows would run unconfined after an upgrade without the sink change.
5. Mixed missions launder isolated output through ordinary *executions*, not only through verification (Q2).
6. `run_check` hands the project's commands Core's entire environment (`local.py:499`). A6's confined verifier will need T-033's pinned-environment treatment; noted for A6, not K5a.
7. A PASSED with revision None on a task-branch execution leaves the merge looping as a lost race (§5); today unreachable, under K3 it is T-030 Q2's case.
