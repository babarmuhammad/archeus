# T-120 report: P21 slice D (eligible part), metrics_daily (D2), archeus doctor and core.log rotation (D8)

Claude fork, 2026-10-19. Worktree `D:\archeus-t120`, branch `p21-d`. Not pushed, not merged; needs the independent Claude review the card names.

## Line

```
a9f6d7a metrics_daily: stop scanning the event log after every commit
eca904e Number metrics_daily's migration 0018, after slice A's 0017
3caf59e Merge the recovered P21 slice A line into slice D
bef69ec Recover P21 slice d (recovered content, unreviewed)
4d1ec8a Recover P21 slice a (recovered content, unreviewed)   <- merged in by 3caf59e
d0b98d3 P21 gate (approved D0-D14)
```

The `0018` the card asks for cannot sit on slice D's own line: `migrate.migrations()` refuses a gap. So slice D is now built on slice A's recovered line (`recover/p21-a` 4d1ec8a, merged in by 3caf59e). Merge order: A first, then D. If T-118 adds commits on `p21-a`, merging `p21-a` and then `p21-d` stays clean, because D holds an ancestor of A. To review D on its own: `git diff 4d1ec8a..p21-d`.

## What was recovered and what was added

Recovered in bef69ec (audited against the card and the gate, kept):
- `archeus/core/metrics.py`: `compute`, `record` (writer command, `ON CONFLICT (day) DO NOTHING`), `missing_days`, and the `Metrics` WorldLoop worker (`archeus-metrics`, started and stopped in `runtime.py`). The metric list matches plan §28 (`ARCHEUS_V1_REARCHITECTURE_PLAN.md:403-405`) exactly. A figure with nothing to measure is None, and only finished UTC days are computed.
- `archeus/core/doctor.py` and the `doctor` verb (`archeus/cli/main.py`, `claude_sessions/cli.py` V1_VERBS). It checks integrity, schema version, consumer lag over 1000 events, executions stuck for 6 h, and that the hook compiles. Each finding sets one exit-code bit. There is no `--fix`.
- `connection.inspect`: URI `mode=ro`, so doctor cannot checkpoint a WAL that Core crashed out of.
- `core.log` uses a `RotatingFileHandler` (5 MB, 3 backups).
- Tests: 7 in `test_p21_metrics_doctor.py`, plus `test_db_schema.py` updates. Mutants Z40-Z47. The as-built text is in gate §12.

Added:
- 3caf59e: the merge. Conflicts resolved by keeping both sides: the schema test expects `artifact_records` and `metrics_daily`, and the mutant list holds A's Z23-Z29, then D's Z40-Z47.
- eca904e: `0017_metrics_daily.sql` renamed to `0018_metrics_daily.sql`, its header updated, the schema test now expects 18, and the gate §12 text corrected.
- a9f6d7a: **defect fix.** WorldLoop runs `pass_once` after every writer commit. Each pass ran `SELECT MIN(at)` over the unindexed `events` table and read every `metrics_daily` day, so a busy Core scanned the whole log on every commit. The worker now remembers the date it filled through and reads nothing until the date changes.
  - Two new tests: the worker reads nothing until the date changes, and doctor reports a broken hook (DOCTOR_HOOK) plus a newer schema (DOCTOR_SCHEMA). The recovered work tested neither finding.
  - Mutants Z48 and Z49 guard the new tests.
  - Gate §12 updated: nine tests, Z40-Z49.

Not built (as the card says): Health/Attention (D12, waits for P20). Also not built: a `/v1` read of `metrics_daily`. Gate §7 lists "new reads for ... metrics", but Health (D12) is its only reader, and gate §12 records this.

## Doctor never writes (tested)

- `test_doctor_without_a_database_creates_nothing`: the home tree's hashes are unchanged and no database file appears (Z44).
- `test_doctor_on_a_healthy_home_finds_nothing_and_writes_nothing`: the tree's hashes are unchanged except SQLite's own empty `-wal`/`-shm` sidecars. Planted token, hook-token and MCP-key strings never appear in the output.
- `test_doctor_leaves_a_wal_core_crashed_out_of_to_core`: `archeus.db` and its non-empty WAL are byte-identical after doctor runs (Z43).

## Verify

- `test_p21_metrics_doctor.py`: 9 passed. `test_db_schema.py` plus slice D tests: 28 passed after the renumber.
- Doc gates and CLI tests (`judge/test_traceability.py`, `design/test_design_gates.py`, `integration/test_cli_v1.py`, `unit/test_api_structure.py`, `unit/test_paths.py`, `test_db_schema.py`, `test_p21_metrics_doctor.py`, `tests/test_cli*.py`): 163 passed.
- `py tools/mutate_p21.py Z40 ... Z49`: 10/10 killed. Slice A's Z23-Z29 and Z01-Z22 were not re-run here.
- `gen_api_docs.py --check` and `gen_ui.py --check`: current.
- `ruff check archeus tests/v1 tools`: all checks passed.
- Full `tests/v1 -m "not real_process"` without e2e: 4401 passed, 65 failed, 5 errors. 134 of the errors were `WinError 10048`, socket port exhaustion caused by other forks running HTTP tests on this machine at the same time.
  - Re-running the 14 failing files on their own: 317 passed, 3 failed.
  - Two of those (`test_api_errors[GET /v1/missions/{id}/timeline]`, which was 10048 again, and `test_writer_throughput`, which is load-sensitive) pass when re-run alone.
  - The third, `test_tool_removal_units.py::test_F10_...`, fails on `LS`. This failure is outside this slice and was already recorded by the recovered work (T-113's per-tool path field).
- Not run: e2e (slice D has no SPA change), `real_process` tests.

## Files touched by slice D (over slice A, `git diff 4d1ec8a..p21-d`)

`archeus/cli/main.py`, `archeus/core/doctor.py` (new), `archeus/core/metrics.py` (new), `archeus/core/runtime.py`, `archeus/infra/db/connection.py`, `archeus/infra/db/migrations/0018_metrics_daily.sql` (new), `claude_sessions/cli.py`, `docs/architecture/p21-design-gate.md`, `tests/v1/integration/test_db_schema.py`, `tests/v1/integration/test_p21_metrics_doctor.py` (new), `tools/mutate_p21.py`.

None of them is isolation, boundary, credential or auth code. `connection.py` gains only a read-only opener, doctor reads no credential, and `runtime.py` changes only the log handler and the worker's start and stop.

## Correction r1 (2026-10-19, Claude fork)

Review `reviews/T-120-a9f6d7a.claude.md` CHANGES, 1 finding: `doctor.py` let `sqlite3.DatabaseError` escape from `PRAGMA integrity_check` on a malformed or torn main database file, so doctor crashed with a traceback.

- Commit `5ceddf7` on `p21-d`: `archeus/core/doctor.py` catches `sqlite3.DatabaseError` around the whole database inspection and reports it as a `DOCTOR_DB` finding (`FINDING database <path> cannot be read: <error>`). Doctor then goes on to the hook check. The connection is still `mode=ro` and closed in `finally`.
- Test `test_doctor_reports_a_malformed_database_and_writes_nothing[garbage|truncated]` overwrites `archeus.db` with random bytes, and separately truncates it to half. It asserts the DOCTOR_DB bit, the `FINDING database` line, `doctor: exit <code>`, and that no file changed apart from SQLite's sidecars. Both cases failed against a9f6d7a's doctor ("file is not a database", "database disk image is malformed") and pass with the fix.
- Mutant: none added. Slice D's ids Z40-Z49 are all used, and Z50-Z59 belong to slices F and G (T-121). The new test itself fails when the `except` is removed (shown above).
- Verify:
  - `test_p21_metrics_doctor.py` (11), `test_db_schema.py`, `test_cli_v1.py`, `test_api_structure.py`: 44 passed.
  - `mutate_p21.py Z43 Z44 Z45 Z46 Z49`: 5/5 killed.
  - ruff clean.
