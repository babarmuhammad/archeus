# T-015 · Gap B / H2: caller and state matrix, and the exact patch scope

Prepared by Claude, 2026-10-12. Analysis only: no code, no test run, no OS call. The card is `proposed`; implementation waits for an owner `auth:` naming the scope in §5.

Sources, all in worktree `D:\archeus-pv20-s2-l` at `8997446` (`pv20-s2`):
- contract: `docs/architecture/pv20-execution-isolation-design.md` §3.3 (lines 221-241), §6 items 16 and 24 (595-597, 634-639), §7.4 Gap B (814-823), acceptance row 15 (504, 899); `docs/architecture/state-machines.md` 369-382; `p11-design-gate.md` 240; `p12-design-gate.md` 317;
- code: `archeus/core/application/executions.py` (`record_end` 221-270, `record_handoff` 518-560), `archeus/core/domain/states.py` 163-200, `archeus/core/execution/manager.py` (`_collect` 499-535, `_reconcile_one` 653-697, `_reconcile_isolated` 709-753, `_collect_gone` 806-823), `archeus/harnesses/claude_code/adapter.py` (`status` 188-202, `collect_result` 216-235), `archeus/harnesses/hook.py` 49-65, `archeus/core/application/work.py` 382-393;
- tests: `tests/v1/unit/test_execution_units.py` 183-190, `tests/v1/unit/test_pv20_isolation.py` 836-890.

## 1. What the contract asks, and of whom

- **H2 / A7.** Core's classification is the authoritative halt state. The hook's halt and PreCompact records are untrusted reports that may move a classification **only toward non-advancing**. ENDED_OK is recorded only from Core's own observed exit 0 of an execution that was RUNNING with no outstanding Core control request. From PAUSING an exit resolves to PAUSED, from HANDING_OFF to ENDED_HANDOFF, "or either to ENDED_ERROR on a non-zero exit" (design 233-241). A stream `result` is never a process exit.
- **Scope as written.** `state-machines.md` 369-370 introduces those guards with "For an execution launched under PV-20 isolation, the diagram is read with these guards". For unisolated executions the earlier rulings stand unchanged: "the work finished before it reached a boundary" → `PAUSING → ENDED_OK` (p11 240) and the same for HANDING_OFF (p12 317). This note follows that scoping. Applying H2 to unisolated executions too would be a new ruling (Q3).
- **Gap B** (design 814-823) is the case where `halted.json` is never written (the execution cannot write it, or the write fails and `_halted` swallows it). Today Core then reads "no halt" and can record ENDED_OK.

## 2. Where an end is decided, and what each input is

| Caller | Line | Reaches | For |
|---|---|---|---|
| `manager._collect` | 522-535 | `record_handoff` when HANDING_OFF and not `clean`; otherwise `record_end` | live process ended (isolated and unisolated) |
| `manager._reconcile_isolated` | 736-745 | `record_end(halted=True)` for PAUSING; `record_end(killed=True)` for STOPPING/HANDING_OFF | Core restart, isolated record present |
| `manager._collect_gone` → `_collect` | 806-823 | as `_collect` | Core restart, **unisolated only** (`_reconcile_one` returns into `_reconcile_isolated` first, 664-666) |
| `work.record_exit` | 382-393 | `record_end` | no production caller in `archeus/`; tests only (`test_skeleton`, `test_policy`, `test_routing`, `test_account_protection`) |

| Input to `record_end` | Source | Authority under §3.3 |
|---|---|---|
| `exit_code`, live | `adapter.status`: `child.poll()` on the Popen Core holds (adapter 189-192) | Core observation |
| `exit_code`, after restart | `ended` tombstone (adapter 196), else **the stream's last `result.is_error`** (adapter 199-201) | tombstone: Core's; stream: execution-authored. Reached only through `_collect_gone`, so unisolated only today |
| `halted` | `os.path.exists(req/halted.json)` (adapter 228) | execution-authored report |
| `killed` | Core's own `_stopped` set (adapter 229) | Core |
| `failure`, `summary` | stream content | report; only ever downgrades `ok` |

## 3. Isolated end matrix: today versus A7

| State at end | Exit (Core-observed) | Halt report | Today | A7 | |
|---|---|---|---|---|---|
| RUNNING | 0 | no | ENDED_OK, task → VERIFYING | same | keep |
| RUNNING | 0 | yes | ENDED_ERROR, charged ("halted without being asked") | non-advancing | ok |
| RUNNING | ≠0 or none | any | ENDED_ERROR | same | ok |
| PAUSING | 0 | yes | PAUSED (`halted_at_boundary`, executions 242-245) | PAUSED | ok |
| PAUSING | 0 | **no** | **ENDED_OK** (executions 260-270; edge states.py 191) | PAUSED | **D1** |
| PAUSING | ≠0 | no | ENDED_ERROR | ENDED_ERROR | ok |
| PAUSING | ≠0 | yes | PAUSED (the report wins, executions 242) | text says ENDED_ERROR | **Q2** |
| HANDING_OFF | 0 | no | **ENDED_OK** (`_collect` 522 counts it `clean`, routes to `record_end`; edge states.py 182) | ENDED_HANDOFF | **D2** |
| HANDING_OFF | 0 | yes | ENDED_HANDOFF (`record_handoff`) | same | ok |
| HANDING_OFF | ≠0 or killed | any | ENDED_HANDOFF, uncharged, continuation | text says ENDED_ERROR | **Q1** |
| restart PAUSING | none | not read | PAUSED (Core passes `halted=True`, manager 736-740) | PAUSED or failed: policy detail | ok |
| restart HANDING_OFF / STOPPING | none | not read | ENDED_ERROR / ENDED_KILLED (`killed=True`) | non-advancing | ok |
| restart RUNNING | none | not read | LOST | non-advancing | ok |

D1 and D2 are Gap B: the only thing standing between a PAUSING or HANDING_OFF execution and ENDED_OK is an execution-written file. The report-absent rows are also what a hook that never ran produces. Every report-present row is already non-advancing, so H2's "a forged report only moves toward non-advancing" holds today; nothing to change there.

Not verified: the exit code of a Claude Code process that a hook halts with `continue: false` (hook 49-65). Q1 and Q2 turn on it: if a halted CLI exits non-zero, the literal "ENDED_ERROR on a non-zero exit" would make every cooperative pause and hand-off an error.

## 4. Smallest patch

Isolation is known only to the manager (`_isolation_record`, manager 699-707); `record_end` does not see it. Rather than adding a field to the Execution entity (schema change), the manager passes it.

1. `executions.record_end(..., isolated=False)`:
   - `if e.state == 'PAUSING' and (halted or (isolated and exit_code == 0 and not killed))` → `halted_at_boundary` (D1);
   - `ok = exit_code == 0 and not killed and not halted and not (isolated and e.state != 'RUNNING')`, so an isolated HANDING_OFF exit 0 that reaches `record_end` by any route ends ENDED_ERROR rather than ENDED_OK (fail-closed backstop for D2).
2. `manager._collect`: `iso = self._isolation_record(e.id) is not None`; route `e.state == 'HANDING_OFF' and (not clean or iso)` to `record_handoff` (D2 → ENDED_HANDOFF); pass `isolated=iso` to `record_end`.
3. No change to `states.py`: the two `→ ENDED_OK` edges stay because unisolated executions still use them (p11 240, p12 317), and `test_execution_units.py` 183-190 pins the table as is.
4. No change to `_reconcile_isolated`, the adapter, the hook or `work.record_exit` (default `isolated=False`).

Q1/Q2 are left as today unless the owner rules; both are non-advancing either way.

## 5. Exact scope to authorize, and acceptance tests

Files: `archeus/core/application/executions.py`, `archeus/core/execution/manager.py`, `tests/v1/unit/test_execution_units.py`, `tests/v1/unit/test_pv20_isolation.py`. The card's candidate list names `tests/v1/integration/test_execution.py` instead of `test_pv20_isolation.py`; the isolated manager fakes (`_manager_with_fake_node`, 805-828) live in the latter, so the tests below go there. No overlap with T-016 or T-017 (analysis files only).

Fake tests, no process, no OS call:
- `record_end` level (`test_execution_units.py`): isolated PAUSING exit 0, no report → PAUSED; isolated PAUSING exit 0, report → PAUSED; isolated PAUSING exit 1 → ENDED_ERROR; isolated HANDING_OFF exit 0 via `record_end` → ENDED_ERROR, never ENDED_OK; isolated RUNNING exit 0 → ENDED_OK and the task only reaches VERIFYING; isolated RUNNING exit 0 with report → ENDED_ERROR charged; **unisolated** PAUSING exit 0 and HANDING_OFF exit 0 → ENDED_OK, unchanged.
- `manager._collect` level (`test_pv20_isolation.py`): isolated HANDING_OFF, exit 0, no `halted.json` → `record_handoff` is called and `record_end` is not; isolated PAUSING, exit 0, no `halted.json` → `record_end(isolated=True)`.
- Mutants, each must fail a test: drop the `isolated` pass-through in `_collect`; drop the `or iso` routing; drop the PAUSING exit-0 clause; drop the `ok` backstop.

Verify: from the worktree, `py -m pytest -m "not real_process" tests/v1/unit/test_execution_units.py tests/v1/unit/test_pv20_isolation.py tests/v1/integration/test_execution.py -q`, plus the T-003 S2 set.

## 6. Questions for the owner (not answered here)

- **Q1.** Isolated HANDING_OFF ending with a non-zero exit or killed: keep ENDED_HANDOFF with a continuation (today, p12), or ENDED_ERROR as A7's sentence reads? Both are non-advancing.
- **Q2.** Isolated PAUSING with a halt report and a non-zero exit: keep PAUSED (today), or ENDED_ERROR? Depends on the unverified halted-CLI exit code above.
- **Q3.** Do H2's guards apply to unisolated executions as well? `state-machines.md` scopes them to isolated; extending them reverses p11 240 and p12 317 and would need the two `states.py` edges removed.
- **Q4.** `adapter.status` derives an exit code from the stream's `result` after a restart (adapter 199-201), which A7 says is never an exit. It is reachable only for unisolated executions today. Fix it here, leave it under Q3, or make it its own card?

## 7. Seen in passing, not in this card

`tests/v1/unit/test_pv20_isolation.py:848`, `assert ('killed',) or True`, can never fail: `test_live_isolated_process_is_killed_never_adopted` does not check the kill it is named for. One-line fix in a file this card would touch; listed so it is not lost.
