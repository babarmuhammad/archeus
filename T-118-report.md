# T-118 — P21 slice A (provenance D4/D11, producer record D5): report

Fork, 2026-10-19. Worktree `D:\archeus-t118`, branch `p21-a`. Not pushed. BOARD.md not edited.
Stopped by the owner at 18:22 local time, before the 18:40 deadline.

## What the recovery held (4d1ec8a, on gate d0b98d3)

Most of the slice was already in the recovered commit. The targeted tests passed on it unchanged.
- D4 served model: `Execution.served_model` / `served_level` / `model_revision`,
  `entities.PROVENANCE_LEVELS`, REQUESTED set at `work.new_execution`, the Claude Code adapter's
  `model` event and `billed` list, `manager._billed`, `executions._served` (a level is never
  lowered; a revision is named only at SERVED/BILLED).
- D11: `requirements._source` in `call_snapshot` and `task_snapshot`, `REQ_SOURCES` / `REQ_IDENTITY`.
- D5: `ArtifactRecord` (prefix `arc`), migration `0017_artifact_records.sql`, `record_artifact`,
  `artifact.recorded`, checkpoints recorded by `checkpoint.derive`, `artifacts` in the execution view.
- ADR-0047 clause 5(ii): `no_progress` passes the recorded artifacts to `pressure.progressed`.
- Schema, `generated.ts`, `presentation.ts` ID_KINDS, api-reference, tests, mutants Z23–Z29.

## What I added

- `419d478`: ADR-0031 §6 / ADR-0033 §2 snapshot fields. `installed_version` per harness in
  `input_snapshot` (from `HarnessInfo.version`; None for Claude Code, which reports no version).
  `RouteDecision.task_family` (None) and `capability_snapshot` (`{}`), both frozen. The adapter
  skips `<synthetic>` models. The `record_progress` condition is split back onto separate lines.
  Tests extended: adapter contract (synthetic), `test_I_H3` (installed_version, task_family,
  capability_snapshot). Gate `p21-design-gate.md` §12.A as built, which explains why catalogue
  row versions are not recorded: no versioned catalogue exists before P22.
- `0f4d007`: Z13's snippet in `tools/mutate_p21.py` was stale. The base had renamed
  `guarded` to `refused`, so the whole suite stopped at the snippet check. Fixed, and Z13 is now killed.

## Verify (Windows, this machine)

- Targeted suites (domain, execution units, contract, db_schema, routing, context_capacity,
  execution, design gates, traceability, paths): 664 passed, 2 skipped, 1 xfailed.
- `gen_api_docs.py --check`, `gen_ui.py --check`: current. `ruff check archeus tests/v1
  tools/mutate_p21.py`: clean.
- Mutants Z23–Z29: 7/7 killed (before 419d478). Z13: killed after the fix.
- The first full `tests/v1` run (without e2e) showed 67 failed and 3 errors while the other forks
  were running suites on the same machine. On rerun in isolation:
  - judge + `test_api_errors` + tool_removal: 352 passed, 1 failed.
  - unit + integration + contract + design + tui: 4267 passed, 1 failed.
  The one failure both times is `test_tool_removal_units.py::test_F10_...` (AssertionError: LS),
  and it also fails on the base `d0b98d3`, so it was there before this slice. It is probably the
  same Windows path resolution problem as T-122.

## Not done

- The full `tools/mutate_p21.py` (Z01–Z29) was not re-run after the Z13 fix; the owner's stop
  came first.
- E2E and client tsc/node tests were not run. The slice changes the SPA only through generated
  types and ID_KINDS.
- No independent review yet (the card asks for an independent Claude reviewer).

## Touched files (whole slice, 4d1ec8a^..0f4d007)

archeus/api/schemas.py, archeus/core/application/{executions,resources,work}.py,
archeus/core/domain/{entities,events,ids}.py, archeus/core/execution/{checkpoint,manager}.py,
archeus/harnesses/claude_code/adapter.py (the stream normaliser only),
archeus/infra/db/migrations/0017_artifact_records.sql, archeus/infra/db/rows.py,
clients/app/src/api/generated.ts, clients/app/src/state/presentation.ts,
docs/architecture/{api-reference,p21-design-gate}.md, tests/v1/contract/test_adapter_contract.py,
tests/v1/integration/{test_context_capacity,test_db_schema,test_execution,test_routing}.py,
tests/v1/unit/{test_domain,test_execution_units}.py, tools/mutate_p21.py.
None of these is isolation, boundary, credential or auth code. The slice does not touch
`archeus/node/isolation.py`, the hook, `authorization.py` or any credential path.

## Next step

1. Run `py tools/mutate_p21.py` (all 29) on `0f4d007` with nothing else running.
2. Get the independent Claude review of `4d1ec8a^..0f4d007`.
3. At integration, migration 0017 belongs to slice A; slice D renumbers to 0018 and F/G use 0019.
   Slices C, D and F/G will probably also append a §12 to the gate doc, so expect a merge conflict there.
