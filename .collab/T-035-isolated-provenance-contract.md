# T-035 · Durable isolated provenance: minimal persistence contract

Card T-035 (analysis only). Written 2026-10-13 by a Claude fork, read-only. Code citations are at worktree commit `7675095` (`git show 7675095:<path>`), each grep-checked. Refs: T-030 Correction C-1012-T030 §2 (K2/K5 provenance) and C-1012-T030-2, T-021/T-023 (one early decision), T-026 (accounting).

## 0. What this note does and does not do

- It pins one write-once Execution field, `isolated`, and the one seam that writes it (`manager._spawn` → `executions.prepare_process`), with its rules for first preparation, resume, legacy rows and refusals.
- It separates a **persistence-only** code card (P1, §8) from the readers that would later act on the field: lifecycle fallback (P2), the A6 verification guard and `Mission.isolated_output` (T-030 K5). P1 changes no reader.
- It does not authorize any implementation, schema migration, bulk backfill, verification-policy change, native call or production switch. T-027's refusal and every native/production gate stay as they are.
- **The field is never evidence that confinement happened.** It records Core's isolation *decision* at preparation. A process may never have started after it (§4 rows 7-9), and what an isolated process was actually confined by is S2-G/T-004 and T-008's question, not this field's.

## 1. Today: no durable provenance

| Fact | Where (at `7675095`) |
|---|---|
| The decision is taken once per process, in `_spawn`, from the node's isolation authority | `manager.py:192-199` |
| `prepare_process` records seq, workdir, branch, hook token hash and inventory only | `executions.py:95-124` (update `116-120`, event `121-123`) |
| The Execution entity has no isolation field | `entities.py:949-1016` |
| The only authority on "this execution is isolated" is Core's isolation record | `manager.py:731-737` (`_isolation_record`) |
| `requested` answers True for any execution with a record, otherwise asks `authorize` | `isolation.py:552-563` (record test at `557`) |
| `_collect` takes T-022/T-026's `isolated` from the record | `manager.py:545`, passed at `565` |
| Boot reconciliation chooses the isolated path from the record | `manager.py:694-696`; `_reconcile_isolated` passes `isolated=True` at `768-769` and `773-774` |
| Teardown deletes the record once the profile is seen gone; reclaim skips executions still live | `isolation.py:815-847` (`teardown`), `943-947` (`_remove_record`), `1018-1046` (`reclaim`, `live` skip) |
| Verification reads executions but never isolation | `worker.py:190`, `worker.py:229`; `reviewer.py:65`, `reviewer.py:86` |

So the record exists for as long as the execution is non-terminal (the manager's sweep passes every non-terminal execution as live, `manager.py:105-110`, `806-809`), and is gone after teardown. After that, and whenever the record file is lost, nothing in Core says the execution ran under an isolation decision.

## 2. The field

**`Execution.isolated: bool = None`**, declared beside `inventory_sha256` (`entities.py:1010`).

**Storage, no migration.** An entity table holds `id`, the promoted columns, row metadata and `body`, every other field as JSON (`rows.py:1-8`). `executions` promotes only `id`, `task_id`, `mission_id`, `attempt`, `state` and the metadata (`migrations/0002_work.sql:41-54`), so `isolated` lives in `body`, exactly as `inventory_sha256` and `charged` (`entities.py:996`) do. `rows.encode` writes it with the rest of the body (`rows.py:84-92`); `rows.decode` loads the body and builds the entity through `from_dict` (`rows.py:95-99`), so **a row written before the field existed has no key and reads as `None`** (the dataclass default).

**Forward-only.** `from_dict` refuses unknown keys (`entities.py:142-146`), so an older build reading a row that carries `isolated` fails to decode it. That is the same, already-accepted property every body field added since P11 has (`inventory_sha256`, `end_state_digest`, `context`); no downgrade path is promised.

**Validation.** `Execution._check` (`entities.py:1013-1015`) gains: `isolated` is `None` or a real `bool` (an `isinstance(v, bool)` check, so `1`/`0` are refused).

**Write-once is enforced in the one writer, not by `_FROZEN`.** `_FROZEN` fixes a field from the insert onward (`entities.py:43-44`), but the INTENT row is inserted before any decision exists, so it cannot express "fixed after the first preparation". `prepare_process` is the only command that writes the field (§3); no other command names it.

**Semantics, readable from the row alone:**

| `isolated` | `process_seq` | Meaning |
|---|---|---|
| `True` / `False` | ≥ 1 | Core's isolation decision for this execution, recorded at its first preparation; every later process of it was prepared under the same decision (§3 rule 2) |
| `None` | 0 | Never prepared: no process of it was ever about to start |
| `None` | ≥ 1 | Prepared before the field existed (legacy), or a process recorded through the P3.5 test entry `work.record_spawn`, which bypasses `prepare_process` (`work.py:371-380`; no product caller). **Unknown** |

## 3. The seam and its rules

`manager._spawn` already holds the one decision (`manager.py:192-199`) and calls `prepare_process` at `manager.py:254-256`. P1 adds `isolated=isolated` to that call. `prepare_process` gains a **required** keyword-only `isolated` (a `bool`; `None` refused as `ValueError`), so a caller that forgets it fails instead of recording "unknown". Today's only other caller is the E61 test (`tests/v1/integration/test_execution.py:798-802`), which passes `isolated=False`.

Rules, applied in order after the existing state check (`executions.py:103-105`) and sequence check (`106-108`), **before** the binding check (`109-112`) and before any write:

1. **First preparation** (`e.process_seq == 0`): the update writes `isolated`.
2. **Later preparation with a recorded value** (`e.process_seq ≥ 1`, `e.isolated` is a bool): the decision must equal it. A mismatch is **refused** through the existing `refuse(..., stop_reason='binding')` path, with the reason "its isolation decision changed (recorded X, now Y)", and returns `refused` exactly as the binding refusal at `executions.py:109-112` does. Nothing of the row is updated first. Uncharged; the task goes back to READY and is dispatched as a new execution with its own fresh decision (`refuse`, `executions.py:127-143`).
3. **Later preparation of a legacy row** (`e.process_seq ≥ 1`, `e.isolated is None`): nothing is compared and nothing is written; the field stays `None`. Writing `False` here would confirm "ordinary" for earlier processes nobody recorded, which the card forbids; writing `True` would claim a decision those processes may not have had.

The update dict gains one line, `'isolated': isolated if e.process_seq == 0 else e.isolated,`, inserted **above** the `inventory_sha256` line. `tools/mutate_p20.py:318` (Q57) anchors on `executions.py:119` verbatim, so that line must not change; `tests/v1/unit/test_mutation_suites_parse.py` belongs in P1's verify set.

The `execution.prepared` payload (`executions.py:121-123`) gains `'isolated'`. Its consumers only read other keys (`tests/v1/integration/test_settings_sources.py:199-200` reads `inventory`; `tests/v1/integration/test_execution.py:124-125` keys on the type), so the addition is compatible. The event type's description string (`events.py:43-44`) already omits `inventory`; updating it is optional.

**Why a refusal and not `IllegalTrigger` (this supersedes T-030 §2's wording for this field).** The manager's pass catches `errors.LOST_RACE`, which includes `IllegalTrigger` (`errors.py:16`), logs it as a lost race and moves on (`manager.py:119-124`). A PAUSED execution whose resume raised would stay PAUSED and be re-attempted, and re-refused, on every pass. Refusing through `refuse` ends it once, uncharged, which is also the existing precedent for "the resume's footing changed": `resume_checked` discards a resume whose binding, authorization or route changed with `stop_reason='binding'` (`executions.py:732-762`, refusal at `760-761`).

## 4. Every case

| # | Case | Field after | Behaviour |
|---|---|---|---|
| 1 | First preparation, decision True or False | that bool | written with the rest of the preparation; payload carries it |
| 2 | Resume (PAUSED or AWAITING_APPROVAL → `_resume`, `manager.py:604`), same decision | unchanged | accepted |
| 3 | Resume, recorded True, decision now False (e.g. the record file was lost while PAUSED, so `requested` falls through to `authorize`, `isolation.py:557-563`) | unchanged (True) | refused (`binding`, uncharged); the execution ends ENDED_KILLED; a new execution is dispatched under a fresh decision. An isolated session is never resumed unisolated |
| 4 | Resume, recorded False, decision now True (an unisolated execution later approved by `authorize`) | unchanged (False) | refused the same way. This is the fail-closed interim for T-016 W7's migration rule; W7 may later decide something else |
| 5 | Resume of a legacy prepared row (`None`, `process_seq ≥ 1`) | `None` | accepted, not compared, not written (§3 rule 3) |
| 6 | Refused before preparation: provider terms (`manager.py:183-186`), decision raised (`194-199`), workspace including T-027's isolated-project refusal (`200-205`), inventory (`247-252`), or `prepare_process`'s own binding refusal (`executions.py:109-112`) | `None`, `process_seq` 0 | never prepared; no process, no verification. Not written on purpose: the field records a preparation, and none happened |
| 7 | Prepared, then disarmed before the spawn (`manager.py:259-262`) | the bool | refused afterwards; nothing started. The field still records the decision, not a process |
| 8 | Prepared, then `SpawnFailed`/`AlreadySpawned` (`manager.py:268-279`) | the bool | refused `binding`; nothing started |
| 9 | Prepared, then Core crashed before the spawn (E61, `test_execution.py:798-806`) | the bool | ABANDONED uncharged at boot; nothing started |
| 10 | Hand-off continuation or retry | its own value | a new Execution row, `None` until its own first preparation, then its own decision (T-023's decision is per execution) |
| 11 | Core restart, execution non-terminal, record present | the bool | reconciliation unchanged in P1 (record still decides, `manager.py:694-696`) |
| 12 | Core restart, execution non-terminal, record **gone**, field True | True | **P1 changes nothing here**: `_reconcile_one` still takes the ordinary path, which can adopt a live process and read `halted.json` as authority. P2 (§8) closes this from the field |
| 13 | After teardown (execution ended) | the bool | durable; this is what K5's A6 guard and `Mission.isolated_output` later read |

## 5. Readers, and what each must do with `None`

P1 itself adds no reader. Every Execution read decodes the field automatically, and the API's execution view, which serialises the whole entity through `queries.view` (`queries.py:13-16`, used by `executions.view`, `executions.py:797-810`), starts returning it. The `Execution` schema is open (`api/schemas.py:508`), so no schema change is required; adding `'isolated': {'type': 'boolean', 'nullable': True}` to it is optional documentation.

Later readers, each in its own card and each with its own `None` rule:

| Reader (later card) | Where today | Rule for the field |
|---|---|---|
| P2 · lifecycle end rules: `_collect`'s `isolated` (T-022/T-026) | `manager.py:545`, `565` | isolated if the record exists **or** `e.isolated is True`. `None` with no record keeps today's ordinary rules (legacy compatibility, §6) |
| P2 · boot reconciliation | `manager.py:694-696`, `_reconcile_isolated` `739-783` | same test; with the record gone, the isolated branch runs without the record's `state`/`failure` checks: kill a live process by identity, never adopt; PAUSING → PAUSED by `core_halt`; STOPPING/HANDING_OFF → `record_end(killed, isolated=True)` |
| K5 · A6 command-check guard | `worker.py:186-192` (task), `226-230` (retry), and the mission paths T-030 §2 names | the legacy unconfined path only when `isolated is False` **exactly**; `None` and `True` go to a human (T-030 §2) |
| K5 · `Mission.isolated_output` | `verification.py:235` (`settle_task`) | set when the settled execution's `isolated` is anything but `False` |

So `None` is never read as confirmed ordinary by a guard: the verification guard fails closed on it, and the lifecycle reader only keeps doing what it does today for rows that predate the field.

## 6. Legacy compatibility effects, stated

- **Executions prepared before P1** keep `None` for their whole life (§3 rule 3); nothing backfills them.
  - Lifecycle (P2): they keep today's behaviour, decided by the record as now. In practice they are ordinary, since production has never dispatched an isolated execution (`PRODUCTION_DISPATCH_ENABLED` is off).
  - Verification (K5): their command checks go to a human once K5 lands, which T-030 §3.2 already accepts as a one-time upgrade cost.
- **Never-prepared rows** (`process_seq` 0) never reach verification, so `None` there affects nothing.
- **Test-only `work.record_spawn` rows** read as unknown; no product path produces them.
- **API consumers** see one new nullable boolean on executions.
- **Downgrade** is unsupported (§2), as for every body field before it.

## 7. Recommended defaults (reversible, not owner questions)

- Mismatch on a later preparation: refuse through `refuse(stop_reason='binding')`, uncharged, rather than raise (§3). Charging it instead would be a one-word change.
- Legacy `None` at a later preparation: proceed and leave it `None`, rather than discarding every legacy PAUSED execution at upgrade.
- `prepare_process`'s `isolated` is required with no default, as T-023 made the node's.
- Field name `isolated`, as T-030 §2 proposed.

## 8. Proposed cards

**P1 · Persist the decision (this contract's code card).**

| File | Change |
|---|---|
| `archeus/core/domain/entities.py` | `Execution.isolated: bool = None` with a one-line comment that it is Core's decision at preparation, not evidence of confinement; `_check` rejects a non-bool |
| `archeus/core/application/executions.py` | `prepare_process(..., isolated)` required keyword-only; §3 rules 1-3 before the binding check; one update-dict line above the Q57 anchor; payload key |
| `archeus/core/execution/manager.py` | `isolated=isolated` at the `prepare_process` call (`254-256`) only |
| `tests/v1/integration/test_execution.py` | E61 passes `isolated=False`; new tests below |
| `tests/v1/unit/test_execution_units.py` | `_seeded` gains `isolated=None, process_seq=0` keywords; new tests below; the T-023 rig's order test also asserts `prepare_process` received `isolated=<decision>` (the rig's `do` already logs keyword arguments, `test_execution_units.py:951-953`) |

Fake DB tests (temporary `ARCHEUS_HOME`, real `Database.open()`):
- Integration, through the existing rig (`_intent(x)`, `test_execution.py:207`), which builds the full binding that `prepare_process` checks (`executions.py:74-90`); the unit `_seeded` helper has no policy decision and cannot pass it:
  - first preparation with True and with False: the row and the `execution.prepared` payload carry it;
  - a second preparation from INTENT (`process_seq` 2) with the same value: accepted, value unchanged;
  - a second preparation with the other value, both directions: ABANDONED, `stop_reason` `binding`, `charged` False, task READY, `isolated` and `process_seq` unchanged;
  - a legacy row (body update setting `process_seq` 1 and no `isolated`) prepared again with True and with False: accepted, field still `None`.
- Unit, on `_seeded('PAUSED', isolated=True, process_seq=1)`, relying on the mismatch check running before the binding check:
  - preparation with False: ENDED_KILLED, `charged` False, task READY, field still True;
  - preparation with True: refused for the binding reason, not the mismatch one, which shows the comparison passed;
  - `Execution(..., isolated=1)` raises; `Execution.from_dict` without the key gives `None`.
- Mutants on a throwaway copy: first write dropped; every preparation overwrites; mismatch accepted; mismatch raised as `IllegalTrigger`; legacy `None` overwritten with False; payload key dropped; manager passes a constant.
- Verify: `py -m pytest -m "not real_process" tests/v1/unit/test_execution_units.py tests/v1/integration/test_execution.py tests/v1/unit/test_mutation_suites_parse.py -q`.

Not in P1: no reader, no `record_end`/`_collect`/reconcile change, no verification, mission, schema, isolation-module or migration change.

**P2 · Lifecycle readers fall back to the durable field (separate card, after P1).** `manager.py` only (`_collect` at `545`, `_reconcile_one` at `694-696`, `_reconcile_isolated` accepting no record), plus tests that delete the record of a non-terminal isolated execution and assert no adoption, PAUSING → PAUSED, and isolated end rules. Without P2, case 12 of §4 stays as today.

**K5** (T-030) owns the A6 guard and `Mission.isolated_output`, reading the field under §5's rules.

Dependencies: P1 has none beyond T-023 (done). P1 edits `executions.py`, `manager.py` and `test_execution_units.py`, so it serializes with any other card holding those files (T-033 currently holds `manager.py` for its `CAPABILITY_ENV` import).

## 9. Owner questions

1. Authorize P1 (persistence only: the field, its write-once rules in `prepare_process`, the manager pass-through, and the tests in §8) ahead of the rest of K2? It changes no reader and no behaviour except the uncharged refusal of a resume whose isolation decision changed (§4 rows 3-4).
2. Authorize P2 after P1, so that a lost isolation record no longer sends a live isolated execution down the ordinary reconcile path (adoption, `halted.json` as authority)? Or should that wait for K-series acceptance?
