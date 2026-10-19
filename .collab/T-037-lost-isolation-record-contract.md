# T-037 · P2: lost transient isolation record — lifecycle contract

Card T-037 (analysis only). Claude (fork), 2026-10-13, read-only. Code citations are at the reviewed S2 baseline `894c0bd` (`git show 894c0bd:<path>`), each line checked. The durable field is **pending T-036: `Execution.isolated: bool | None`, written at `prepare_process`, legacy `None`** (T-035 §2-§3); nothing here reads T-036's in-progress diff. Refs: T-035 §4 row 12, §5, §8 (P2); T-022 (H2/A7 live-end rules, Core-owned restart halt); T-026 (C1 accounting); T-019 (restart kill); T-030 C-1012-T030-2 (no import after a restart); R6-A, R7.

## 0. What this note does and does not do

- It maps every reader of Core's transient isolation record (`run/isolation/<id>.json`), says what each does when the record is present, invalid or missing, and pins what the lifecycle must do when the record is missing but the durable field says the execution was isolated.
- It proposes one implementation card (P2, §9), `manager.py` plus fake-rig tests.
- It authorizes nothing: no lifecycle change, no verifier or mission reader, no grant, no native call, no new record or ledger format, no activation. `PRODUCTION_DISPATCH_ENABLED` is off, so production has never dispatched an isolated execution: every case below is latent today and reachable only through test harnesses Core authorized.
- The field is Core's **decision** at preparation. It is never evidence that confinement happened, and P2 must not read it as such (§8).

## 1. Terms

- **Record**: Core's isolation record, `isolation.py:367-415`, at `paths.isolation_state` (`paths.py:102-107`), deliberately outside the execution's directory. It carries the identity, `owned` (Core created the profile), the six invariant `conditions` checked at establishment, and the launched `pid`/`create_time` (`isolation.py:1181-1183`). It is written by Core but, like everything under `ARCHEUS_HOME`, writable by any process of the same user.
- **Field**: the durable `Execution.isolated` (pending T-036).
- **Process evidence**, three grades:
  - **(A) verified identity**: Core's own process handle while this Core launched it (`adapter._children`, `claude_code/adapter.py:177`, `194-197`; `Isolation._live`, `isolation.py:897-899`), or after a restart a Core-recorded `(pid, create_time)` from `pid.json` (`base.py` `spawn`, written by Core) that the OS confirms: `LocalNode.alive` requires a create time and a match (`local.py:115-118`), and `kill` re-checks it (`local.py:120-129`; `proc.kill_pid_tree` refuses a `None` or mismatching create time, `claude_sessions/proc.py:257-276`).
  - **(B) PID only / registry claim**: a `pid.json` without a create time (`alive` answers False), or a line in `run/processes.jsonl`. The registry is "the instrument, never the authority" (`isolation.py` `_note`, `local.py` `spawn` docstring). Reconciliation never builds a handle from it; the one reader that kills from it is the e-stop without Core (`local.py:220-236`), with a create-time check, outside this card.
  - **(C) no process**: no `pid.json` for the current `process_seq`.

## 2. Readers of the record, at `894c0bd`

`Isolation.record` returns `None` **only** on `FileNotFoundError` (`isolation.py:577-578`). An unreadable file, a malformed one, or one that does not derive from the execution id comes back as `state='invalid'` with only the derived identity (`579-587`), so "invalid" already counts as isolated everywhere below. Only "missing" flips anything.

| Reader | Present (valid) | Invalid | Missing |
|---|---|---|---|
| `Isolation.requested` (`isolation.py:552-563`), called once per spawn by `manager._spawn` (`manager.py:189-196`) | True (`557-558`), so a resume stays isolated (R7) | True | falls through to `authorize`; False for any real harness while production dispatch is off |
| `manager._collect`, live end (`manager.py:542-548`) | H2/A7 rules: hand-off only on exit 0 and not killed; `record_end(isolated=True)` (`557-562`), which gives T-026 C1 and ignores `halted` for PAUSING/HANDING_OFF (`executions.py:235-258`) | same | **ordinary rules**: `handoff = exit != 0 or halted or killed` (`548`), so an unclean hand-off goes to `record_handoff` (ENDED_HANDOFF plus a continuation, `executions.py:531-569`), and a PAUSING end is PAUSED or charged ENDED_ERROR depending on `halted.json` (`claude_code/adapter.py:234`, `fake.py:180`) |
| `manager._reconcile_one`, boot and orphan pass (`manager.py:680-726`) | `_reconcile_isolated` (`691-693`) | same; the establishment-failure branch is not taken (`failure` is empty) | **ordinary path**: a live process is adopted (`704-708`, `711-717`, `719-721`); a gone one goes through `_collect_gone` (`833-850`) |
| `manager._reconcile_isolated` (`manager.py:736-780`) | kill a live process by verified identity, never adopt (`749-753`); failure → refuse `binding` (`754-760`); PAUSED/AWAITING → the pass (`761-762`); PAUSING → `record_end(core_halt=True, isolated=True)` → PAUSED (`763-767`); STOPPING/HANDING_OFF → `record_end(killed=True, isolated=True)` (`768-772`); INTENT without a process → refuse `binding` (`773-776`); anything else → `lost` (`777-780`) | same, minus the failure branch | not reached |
| `Isolation.establish` (`isolation.py:667-697`) | `pending`/`established` reused (a resume, R7) | refused `record_invalid` (`675-678`) | a fresh `pending` record (`692`); if the profile still stands, `create_profile` answers `existed` and it is refused as `profile_preexisting` (`720-727`); if it is gone, **a new identity is created** |
| `Isolation.teardown` via `_release_isolation` (`manager.py:782-795`, `isolation.py:815-840`) | Job closed, owned profile deleted once its process is gone, then the record removed (`849-863`, `943-947`) | Job closed, record and profile left as found (`833-835`) | Job closed if this Core holds it (`826-829`), then returns (`831-832`): the profile is never deleted |
| `Isolation.reclaim`/`stale` (`isolation.py:1018-1051`, `1096-1112`) | skipped while live (`1039-1040`, `1111-1112`); torn down once not | left as found (`1083-1084`) | invisible: `stale()` lists record files only. `is_stale_profile` (`isolation.py:93`) has no caller |
| `IsolationContext.facts` → registry spawn line (`isolation.py:1204-1210`, `local.py:75-77`) | `isolated: True` plus identity | same | `{}` (only read at spawn time) |
| Job (`Isolation._jobs`, `isolation.py:789-804`) | in memory only: held by this Core, gone after a restart | — | unaffected by the file: a live Core still closes it at teardown |

Nothing else reads the record. Verification reads executions, never isolation (`worker.py`, `reviewer.py`, per T-035 §1).

## 3. How a record goes missing

Core never removes the record of a live execution. `_remove_record` runs only from `_delete_profile` and `_unowned` (`isolation.py:862`, `932-934`), reached only through teardown on an end path or through `reclaim`, which skips every id in the live set (`1039-1040`, `1111-1112`). The live set is every non-terminal execution read at the start of the pass (`manager.py:102-107`, `134`), so an execution that ends mid-pass is skipped once, never torn down early.

So a missing record on a non-terminal execution means something outside Core's own paths: a same-user process deleting or moving the file (an ordinary execution runs as the user with full access to `ARCHEUS_HOME`), a database restored next to a `run/` it did not come from, or a bug. An isolated execution itself has no grant on Core's state (classes 4-6 stay ungranted, `check_invariant`). The field is what survives all of those, because it lives in the database row.

## 4. Gaps today (record missing, decision was isolated)

- **G1 · Adoption.** A live process is adopted as ordinary (`manager.py:704-708`, `711-717`, `719-721`): Core watches a process whose Job died with the last Core, which R6-A calls a contradiction to be killed.
- **G2 · Report authority restored, twice.** `_collect_gone` takes the exit code from Core's `ended` tombstone or, failing that, from the stream's last `result` event (`claude_code/adapter.py:202-207`), and `collect_result` reads `halted.json` (`234`). Both are written by the execution. So a RUNNING isolated execution killed by Core's death, with a forged or genuine `result` line, ends **ENDED_OK** and its task goes to VERIFYING; with the record present it ends `lost`. T-035 named only `halted.json`; the stream-derived exit code is the second channel.
- **G3 · A7 broken.** An unclean isolated hand-off end reaches `record_handoff`: ENDED_HANDOFF and a continuation built on it, where A7 gives ENDED_ERROR and no continuation. A PAUSING end becomes PAUSED or charged ENDED_ERROR depending on a file the execution writes.
- **G4 · Resume under another identity.** With the record gone and the decision still True (a test harness Core authorizes), T-036's mismatch check passes (same value), and `establish` either refuses the standing profile as `profile_preexisting` (fail-closed, uncharged) or, if the old profile is gone, **creates a new one**, so the resumed session runs under a different principal over the old private config and state. That contradicts R7 ("its resumes reuse its identity"). With the decision now False, T-036 refuses it, but only after `_workspace` and the inventory ran with `isolated=False` (`manager.py:197-250`).
- **G5 · Orphaned profile.** With no record, teardown closes the Job but deletes nothing (`isolation.py:826-832`) and reclaim cannot see the profile. That is the safe direction (no delete without ownership), but it is permanent and silent.

The live-Core variant (file deleted while the process runs, no restart) has G2's `halted.json` half and all of G3 through `_collect`; the Job is still held and still closed at teardown.

## 5. State matrix

Columns are the process evidence of §1. "Isolated outcome" means §7's table.

| Record | Field | (A) verified identity, alive | (B) PID only / registry | (C) no process |
|---|---|---|---|---|
| present or invalid | True | today: killed by identity, never adopted, isolated outcome. **P2: unchanged** | today: nothing killed or adopted, isolated outcome. **unchanged** | isolated outcome. **unchanged** |
| present or invalid | False | today: isolated path, because the record escalates. Only a planted or foreign file produces this. **unchanged**; a resume meets `requested`=True against recorded False and T-036 refuses it, uncharged | same | same |
| present or invalid | None | today: isolated path. **unchanged** | same | same |
| missing | True | today: **adopted** (G1), ordinary end rules (G2, G3). **P2: killed by identity, never adopted, isolated outcome, registry note** | today: not adopted, `_collect_gone` reads tombstone/stream/`halted.json` (G2). **P2: nothing killed, nothing read from the execution, isolated outcome** | today: ordinary `lost` or `_collect_gone`. **P2: isolated outcome** |
| missing | False | ordinary path, which is right: Core decided ordinary and spawned without an isolation context (`local.py:60-61`). **unchanged** | **unchanged** | **unchanged** |
| missing | None, `process_seq ≥ 1` | today: ordinary. **P2 (recommended N1): ordinary rules kept, nothing written, one registry note that provenance is unknown**; see §11 Q1 | same | same |
| missing | None, `process_seq` 0 | never prepared: `_first` (`manager.py:139-141`); not a reconcile case | — | — |

## 6. Rules P2 pins

1. **Isolated for the lifecycle** means: the record exists (valid or invalid) **or** `e.isolated is True`. `None` alone is not isolated for the lifecycle (§11 Q1) and is **never written** as False; `False` with no record is ordinary. Both `_collect` and `_reconcile_one` use this one predicate, so the live end and the restart end cannot disagree.
2. **No adoption** of a known-isolated execution, ever. A live process with a verified identity is killed by that identity (`node.kill`, which re-checks it) and the record-level outcome follows. **No kill and no delete on PID-only evidence**, and nothing is killed or deleted under missing ownership except through a handle Core holds (its own Job, its own process handle).
3. **No report authority** for a known-isolated execution: with the record missing, the restart path never calls `_collect_gone`, `adapter.status` or `collect_result`, so neither `halted.json` nor a stream-derived exit code is read. The live path keeps passing `halted` to `record_end`, where for an isolated execution it can only turn a RUNNING exit 0 into ENDED_ERROR (`executions.py:273`), never the reverse.
4. **No unisolated fallback and no new identity.** A later preparation of an execution with `isolated is True` and no record is refused in `_spawn`, **before** the decision, the workspace and the inventory: `refuse(stop_reason='binding')`, uncharged, task back to READY, a new execution under a fresh decision. This closes G4 in both directions and keeps T-036's comparison as the backstop for False→True.
5. **No record is synthesized** for a live execution. Writing one (for example `failed/provenance_unknown`, as `_unowned` does for an ended one) would route a RUNNING execution into the establishment-failure branch (`manager.py:754-760`), whose refusal exists for INTENT, PAUSED and AWAITING_APPROVAL only (`tests/v1/unit/test_pv20_isolation.py:2229`).
6. **Visible, not silent.** When the field alone decides "isolated" (record missing), and when a `None` row takes the ordinary path, Core writes one registry line per execution per Core process (`isolation_record_missing` / `isolation_provenance_unknown`), through `node._registry` as `_tombstone` already does (`manager.py:824`). The registry stays an instrument: nothing reads these lines as authority.

## 7. Safe outcomes

For a known-isolated execution resolved without its record, or after a restart with it. "Charged" is whether the task spends an attempt.

| Situation | End | Charged | Continuation | Where |
|---|---|---|---|---|
| **Core-caused halt**: PAUSING at restart | PAUSED via `core_halt` (no end) | no attempt spent | none; resumable, but with the record missing the resume is refused by rule 4: ENDED_KILLED, uncharged, task READY | `manager.py:763-767`, `executions.py:255-258`, rule 4 |
| Core-caused hand-off end (HANDING_OFF, any exit but a clean one) | ENDED_ERROR (A7) | **no**: T-026 C1, every hand-off cause plus `handoff_user` is in `UNCHARGED` | **none**: `record_end` never creates one | `manager.py:768-772`, `executions.py:241`, `38`, `478` |
| STOPPING at restart | ENDED_KILLED | only if the stop reason is outside `UNCHARGED` | none | `executions.py:259-264` |
| **Unknown exit**: STARTING, RUNNING, LOST, or INTENT with a process recorded | ENDED_KILLED via `lost` | **yes** (unchanged; §11 Q2) | none | `manager.py:777-780`, `executions.py:329-342` |
| INTENT with no process | ABANDONED via `refuse(binding)` | no | none | `manager.py:773-776` |
| PAUSED / AWAITING_APPROVAL at restart | unchanged; a live unrecorded resume is killed by identity | — | the next resume is refused by rule 4 (record missing) | `manager.py:749-753`, `761-762` |
| **Lost Job** | live Core: still held in memory, closed at teardown (kill-on-close) regardless of the file. After a restart: there is none; a live root is killed by verified identity only, and descendants that left the root's parent chain are not reached (`kill_pid_tree` is a `/T` tree kill by parentage; that is T-030's C6 and T-008's, not this card's) | per row above | none | `isolation.py:826-829`, `manager.py:749-753` |
| **No owned profile** (ownership lived only in the lost record) | never deleted; teardown returns early; the profile stays, invisible to reclaim, under keep-all retention. Rule 4 means no resume ever meets it as `profile_preexisting` | — | — | `isolation.py:826-832`, `1096-1112`; §11 Q3 |

Per T-030 (fence, "no import … every end after a restart"), none of these brings any result back; P2 adds no import. When K3 lands, its import must test isolation with the same predicate as rule 1.

## 8. Three different things

| | What it is | Who writes it | What it may decide |
|---|---|---|---|
| **Decision provenance**: `Execution.isolated` (pending T-036) | Core's decision at the first preparation, durable in the row | `prepare_process` only | after P2: the lifecycle (`_collect`, `_reconcile_one`, the `_spawn` guard). Never ownership, never confinement |
| **Transient record** | Core's bookkeeping of identity, `owned`, Job-era pid, and the invariant `conditions` it checked at launch | `Isolation` only; same-user writable; removed at teardown | the identity, teardown and ownership; evidence of what Core saw, never an authentication (`isolation.py:367-390`) |
| **Evidence of OS confinement** | whether the process actually ran confined: ACLs, Job membership of descendants, outside writers | nothing persists it beyond the record's `conditions` | S2-G/T-004, T-008, T-030 C6. P2 adds none and claims none |
| **Verification semantics** | whether a command check may run unconfined, and `Mission.isolated_output` | K5 (T-030) | the field read as **exactly False** → the legacy path; True or None → a person. P2 adds no verifier or mission reader, and no P2 outcome is evidence that output is safe to verify |

## 9. P2 · proposed card

**Depends on T-036 being committed** (the field must exist). Disjoint from T-034. Holds `manager.py`, so it serializes with any card holding that file.

| File | Change |
|---|---|
| `archeus/core/execution/manager.py` | one predicate (rule 1) used by `_collect` (`542`) and `_reconcile_one` (`691-693`); `_reconcile_isolated` accepts `iso=None` and guards its failure branch with `iso is not None` (`754`); the rule-4 refusal in `_spawn` after the terms check (`180-183`) and before the decision (`189`); rule 6's registry lines, deduplicated per manager instance |
| `tests/v1/unit/test_pv20_isolation.py` | `_e` (`853`) and `TestIsolatedLiveEndRoute`'s execution (`918`) gain `isolated`; a new `TestLostIsolationRecord` on `_manager_with_fake_node` (`838`) |
| `tests/v1/unit/test_execution_units.py` | `_spawn_rig` (`894`): the execution gains `isolated` if T-036 has not added it, the node gains `isolation_record`; the guard tests |

No change to `executions.py`, `isolation.py`, `local.py`, entities, verification, missions or the registry format. `tests/v1/integration/test_execution.py` runs in verify, unedited.

**Tests** (fake rigs; the adapter is `object()` wherever the execution's files must not be read, so any call to `status`/`collect_result` raises):
1. `_collect`, record missing, field True: HANDING_OFF exit 1, exit None and killed → `record_end(isolated=True)`, never `record_handoff`; HANDING_OFF exit 0 → `record_handoff`; PAUSING exit 0, `halted` False → `record_end(isolated=True)`.
2. `_collect`, record missing, field False and None: `test_an_ordinary_handoff_keeps_its_route` parametrized over both, unchanged routes.
3. `_reconcile_one`, record missing, field True, verified identity alive, for RUNNING, STARTING, PAUSING, STOPPING, HANDING_OFF, INTENT, PAUSED, AWAITING_APPROVAL: `node.kills == [(adapter, handle)]`; no `record_process`, `adopted` or `record_handoff`; the §7 command and its `isolated=True` / `core_halt=True` / `killed=True` arguments.
4. Same with a handle whose create time is None and a node whose `alive` honours it: no kill, no adoption, the same outcome.
5. Forged `req/halted.json` and a stream `result` line with `is_error: false` in the execution directory, record missing, field True, RUNNING, not alive: `lost`, never `record_end` with exit 0.
6. Record missing, field None, live RUNNING: adopted as today (N1), plus one `isolation_provenance_unknown` line. Field False: adopted, no line.
7. Record present, field False: `_reconcile_isolated` is taken (the record escalates).
8. `_reconcile_isolated(..., iso=None)` on INTENT without a handle: `refuse(binding)`, no exception.
9. `_spawn` resume with field True and no record: the log is exactly `['refuse']` with `stop_reason='binding'`, before `requested`/`workspace`/`inventory`. Field True with a record, and field False/None without one: the existing order, unchanged.
10. One `isolation_record_missing` line per execution across two reconciles of it.

**Mutants** on a throwaway copy, each to be caught: `_collect` reads the record only; `_collect` treats None as isolated (`is not False`); `_reconcile_one` reads the record only; `_reconcile_one` routes None to the isolated path; failure branch unguarded for `iso=None`; kill without `node.alive`; the lost-record path calls `_collect_gone`; the `_spawn` guard removed; the guard charged (`workspace`); the guard fires for None or False; the guard placed after the decision; the registry line dropped.

**Verify**: from the S2 root, `py -m pytest -m "not real_process" tests/v1/unit/test_pv20_isolation.py tests/v1/unit/test_execution_units.py tests/v1/integration/test_execution.py tests/v1/unit/test_mutation_suites_parse.py -q`. No new process, native or real-CLI test. (No mutation suite anchors on the lines P2 edits: `git grep` of `tools/` for `_isolation_record`/`_reconcile_isolated` at `894c0bd` finds nothing.)

## 10. Recommended defaults (reversible, not owner questions)

- Rule 4 refuses rather than re-establishes, before the decision, with `binding` (uncharged). Re-establishing under a new identity would be an R7 change and is not proposed.
- No record is written for a live execution (rule 5); the orphaned profile is left alone.
- Registry line names `isolation_record_missing` and `isolation_provenance_unknown`, one per execution per Core process. A `log.warning` alone would do the same job less durably.
- `invalid` keeps its current meaning (isolated, failure branch not taken); P2 does not touch it.

## 11. Owner questions

1. **Legacy `None` in the lifecycle.** **N1** (recommended): keep today's ordinary rules for a legacy row with no record, write nothing, leave one registry line. Its cost, stated: a legacy execution that did run isolated and loses its record is adopted and ended by ordinary rules, as today; production has dispatched none, so the population is test-harness executions in development homes, and it shrinks to nothing once rows prepared before T-036 end. **N2**: also treat it as isolated when the registry holds a spawn line with `isolated: True` for it, using the instrument only to raise caution, never to lower it. **N3**: treat every `None` as isolated. Its cost: at the first boot after the upgrade every live legacy ordinary execution is killed rather than adopted, and every ordinary hook-halted pause that exits non-zero becomes ENDED_ERROR (`LIVE_ENDS`, `tests/v1/unit/test_execution_units.py`, the `(False, 'PAUSING', 1, False, True, 'PAUSED')` row). The verification guard fails closed on `None` under all three (T-035 §5).
2. **Unknown exit after a restart.** An isolated execution found STARTING or RUNNING at boot was most likely killed by Core's own death (kill-on-close), yet `lost` charges it. Keep it charged (recommended: bounded retries, and Core cannot tell that kill from an exit before it died), or extend C1 and make it uncharged, which re-dispatches without bound if Core keeps crashing.
3. **Orphaned profile.** Keep it indefinitely under keep-all retention (recommended), or authorize a later reclaim card. That card would need ownership evidence that survives the record, which neither the field nor the registry is.
4. **Authorize P2** (§9) once T-036 is committed?
