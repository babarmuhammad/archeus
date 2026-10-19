VERDICT: CHANGES

Re-review of the T-102 follow-up 0fb5daa (on fadadd7), which takes the non-blocking findings 1 and 2 of reviews/T-102-438d5ca.claude.md. Read-only: no product code edited, nothing committed. Tests ran from a `git archive 0fb5daa` copy.

The accounting is right. `flag_argv` (sources.py:388-397) raises `base.SpawnWriteFailed` when the MCP config cannot be written. The exception passes `LocalNode.spawn` and reaches `_spawn`'s charged `workspace` refusal, so a persistent failure spends max_attempts and the task ends FAILED instead of an exception escaping the tick (exit 3) and coming back uncharged. The parametrised test pins the stale `ended`/`halted.json` removal and the class-dir makedirs, the two mutants that survived last time. One blocking problem: the switch to `config.write_atomic` introduces a copy of the keys that the D7 cleanup can never reach.

Findings:
1. sources.py:394 with claude_sessions/config.py:759-793 and base.py:550-578. Blocking, a D7 (T-099) regression introduced by this commit.
   This answers the brief: yes, `write_atomic` can leave a .tmp file holding the MCP env and headers, and nothing ever removes it. `write_atomic` writes `res/mcp.json.<core pid>.tmp` first, then calls `os.replace`.
   - In-process failure: the except path unlinks the tmp, best effort. If that unlink also fails, the error is swallowed. Probed: with `os.replace` failing, nothing was left; with `os.replace` and `os.unlink` both failing, `mcp.json.<pid>.tmp` was left, with no log.
   - Core dying between `open(tmp)` and `os.replace` (killed, crash, power loss): a complete key file is left under the tmp name.
   `drop_mcp_config`, which both `mark_ended` and the boot `sweep_mcp_configs` use, removes only `paths.mcp`, and nothing in archeus/ ever deletes an exec directory (there is no rmtree). Probed on the archive copy: with `res/mcp.json` and `res/mcp.json.4242.tmp` planted, `sweep_mcp_configs(set())` followed by `mark_ended` removed mcp.json and left the tmp file with its keys.
   Before this commit, an interrupted `open(path, 'w')` left a partial file under the name the sweep removes. The sweep exists precisely for "a Core that died while one ran". So "write_atomic, which leaves no partial file of keys behind" (commit message) holds only for a failure Python sees. On a crash it trades a partial file at the swept name for a complete one at an unswept name. The window is a few milliseconds per MCP spawn, but the invariant is "keys exist only while the execution runs", and the fix is small.
   Fix, either of:
   (a) Drop atomicity here. It buys nothing, because no reader exists until the child is launched. Write with a plain `open(path, 'w')` inside `try/except OSError`, and on failure call `drop_mcp_config` and raise `SpawnWriteFailed`. This keeps the one name every cleanup knows.
   (b) Keep `write_atomic`, and make `drop_mcp_config` also remove `paths.mcp + '.*.tmp'`, so `mark_ended` and the boot sweep reach it too.
   Either way, add a test that plants the tmp file (or kills the write midway) and asserts the sweep leaves no key file.
2. archeus/node/local.py:167-171. Non-blocking, latent, carried over (earlier finding 3).
   `flag_argv`'s `SpawnWriteFailed` is now one more producer that goes through `LocalNode.spawn`'s `except base.SpawnFailed`. On the isolated path that path calls `isolation.note_failure`, which records it as `isolation_failed` while the DB charges `workspace`.
3. Integration note, already on the card: T-103's secrets gate (D:/archeus-p20-h) names `flag_argv`'s `open()` write, so the merge must follow whichever writer finding 1 settles on.

Ran:
- `git -C D:/archeus-p20-mcp archive 0fb5daa` extracted to D:/trv-T105b-src. `py -m pytest tests/v1/integration/test_settings_sources.py tests/v1/integration/test_execution.py tests/v1/integration/test_estop_drills.py -m "not real_process" -p no:cacheprovider --basetemp=D:/trv-T105b`: 110 passed. That includes test_T102_an_mcp_config_that_can_never_be_written_spends_the_tasks_attempts and test_T102_every_write_before_a_child_is_charged[ended|halted|class_dir].
- Scratch probes (a test file in the archive copy only):
  (1) a crash-left `mcp.json.<pid>.tmp` survives `sweep_mcp_configs` and `mark_ended`;
  (2) `write_atomic` failure paths: replace failing leaves nothing, replace plus unlink failing leaves the tmp file, silently.
- `py -m ruff check` on sources.py and test_settings_sources.py: clean. `git show --check 0fb5daa`: clean. No CR in the diff.
- D:/trv-T105b and D:/trv-T105b-src deleted with shutil. D:/archeus-p20-mcp status clean. No test process left running.

Not checked: the card's four mutants (not re-run); the card's 665-test focused set; the full tests/v1; POSIX; the real CLI; the isolated path (read only); a real disk-full or ACL-denied directory, or a real Core kill mid-write (the crash case was simulated by planting the tmp file).

Reviewer: independent Claude agent (general-purpose), 2026-10-15
