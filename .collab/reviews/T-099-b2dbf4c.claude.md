VERDICT: APPROVE

Re-review of the T-099 correction b2dbf4c (detached checkout D:/archeus-p20-mcp; the checkout HEAD is f357434, which touches none of b2dbf4c's product files). Read-only on product code. All four findings of reviews/T-099-56e4c8b.claude.md are fixed as the commit states, and the new tests reproduce. One guard in the new code has no test; it is listed below as non-blocking.

Findings:
1. archeus/core/execution/manager.py:151 and tests/v1/integration/test_settings_sources.py:358-381. Low, test-only, non-blocking.
   Problem: no test covers the `if st.state == 'running': continue` guard in `_orphans`. My mutant deleting it survived test_settings_sources plus test_execution (23 passed). Without the guard, an orphan that is still running gets "collected": `node.ended` writes the `ended` tombstone and the registry `end` line while the process lives, the config is removed from under it, and the entry is popped from `_procs`. `LocalNode.unended()` skips anything with an end line (local.py:278-283), so a later Core-less e-stop would not kill that process.
   Concrete scenario: a halted CLI that is slow to exit after `_stop_account`. The orphan test waits for the exit (:370-375) before it ticks, so the guard is never exercised.
   Required change (can ride with the T-101 correction): tick at least once while the halted process is still running and assert that it is still in `_procs`, that there is no `ended` file, and that the config is present. Then let it exit. A scenario that sleeps after the halt would do it, as would patching status to 'running' for one tick.
2. archeus/harnesses/base.py:317-323. Nit.
   Problem: `except BaseException` covers an OSError while writing the spawning marker or the prompt, but no test exercises that path. A mutant narrowing it to `except SpawnFailed` survived. The prior review asked for either test, so this is optional.
3. tests/v1/integration/test_settings_sources.py:343-345 has three blank lines before the new e-stop test, and :428 has one blank line before the section comment. Nit (ruff's selected rules do not check this).
4. Commit message. Wording nit.
   Problem: it says that after AlreadySpawned "the file is left to that process's end or to the boot sweep". No `_procs` entry exists for that process, so nothing in this Core observes its end. In practice the boot sweep removes the file, and until then the keys stay on disk for the life of that Core. The behaviour is sound; only the description overstates.

Questions asked:
- Prior findings: (1) `_orphans` collects through the same `_collect` once the process has exited. (2) `_start` holds everything before a child exists, and any exception from it drops the config without calling `mark_ended`, so isolation `_fail`'s tombstone is kept. (3) `mark_ended` drops the config in a `finally`. (4) The line is rewrapped. All four are fixed. On a copy with manager.py and base.py reverted to 56e4c8b, 3 of the T099 tests fail (orphan, launch raises, tombstone), and the e-stop and AlreadySpawned tests pass. That matches the card.
- Double collect or race: none found. `_orphans` takes only ids that are not in this tick's `live` snapshot. Entries are added to `_procs` only for live executions (`_spawn`, boot adoption, `_tombstone`), so any id outside the snapshot was already terminal when it was taken. Terminal states are final, and `_collect` pops the entry. `_procs` is touched only on the execution thread; runtime.py:279 only reads its length. A user stop committed by a route thread between the snapshot and `_watch` is handled: `_collect` reloads and returns before `record_end`. `record_progress` on an ended row only updates the offset and usage.
- base.spawn split: (a) Exceptions after `_start` returns a child (`process_create_time`, the pid.json write, base.py:324-325) keep the config while the child lives. That is correct. (b) `IsolatedLaunch.launch` can raise SpawnFailed after `api.launch` has resumed the child, if `base_create_time` or `_save` fails (isolation.py:1588-1591). The config is then dropped while that child is alive for a moment. The manager refuses it and `_release_isolation` closes the kill-on-close Job, so the child is going to die anyway. Acceptable, and latent while isolated dispatch is off. (c) In `spawn_detached` a child exists only once Popen has returned, so no missed path there.
- AlreadySpawned left alone: sound. The marker means a process may hold the file, and the boot sweep is the backstop (see the wording nit in finding 4).
- `mark_ended` finally: correct. In the `_refuse` path the drop runs twice, which is harmless because `FileNotFoundError` is ignored.
- E-stop test: it is a real test. A user e-stop through `Executions.estop`, with the sentinel set, on a RUNNING execution, driven to the end, asserting ENDED_KILLED/estop and no config. The "mark_ended keeps the config" mutant would fail it. It does not cover the AWAITING_APPROVAL e-stop; that belongs to T-101.

Observation (non-blocking; it needs its own card if wanted):
- `_orphans` never kills anything. If an ended execution's process never exits (a halted CLI hanging at shutdown), it stays alive with its config until it exits on its own; with Core up, nothing kills it. Since T-101, an e-stop over an AWAITING_APPROVAL execution whose halt is still exiting lists it in `core.estopped.killed` without issuing a kill. Hooks halt on the sentinel, so no tool runs. This predates the change: an AWAITING_APPROVAL execution with a live process was never killed either. A possible follow-up is `node.kill` on an orphan that is still running, since its execution has already been ended by Core.

Ran:
- In D:/archeus-p20-mcp at f357434: `py -m pytest tests/v1/integration/test_execution.py tests/v1/integration/test_settings_sources.py tests/v1/integration/test_estop_drills.py tests/v1/judge/test_g05_estop.py -m "not real_process" -p no:cacheprovider --basetemp=D:/trv-T101`: 93 passed.
- `py -m ruff check` on the 5 files changed by b2dbf4c and f357434: all checks passed. `git show b2dbf4c --check`: clean.
- On a git-archive copy of f357434 (D:/trv-T101-copy):
  - manager.py and base.py reverted to 56e4c8b: T099 tests 3 failed, 7 passed, as the card states. Then restored.
  - Mutant: running guard in `_orphans` removed. SURVIVED (23 passed).
  - Mutant: `except SpawnFailed` in place of `except BaseException`. SURVIVED (10 passed).
  - Both restored, byte-identical.
- D:/trv-T101, D:/trv-T101-copy and D:/trv-T101-copy-bt were deleted. D:/archeus-p20-mcp `git status` is clean, HEAD f357434.

Not checked: the full tests/v1 suite; the 644-test focused set the card names (not rerun); POSIX; the real CLI; the isolated AppContainer path (read only, not run); two Core instances at once; a Windows file-in-use error on remove.

Reviewer: independent Claude agent (general-purpose), 2026-10-15
