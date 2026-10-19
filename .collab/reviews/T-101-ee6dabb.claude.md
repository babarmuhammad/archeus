VERDICT: APPROVE

Re-review of the T-101 correction ee6dabb (detached checkout D:/archeus-p20-mcp, on top of f357434). I reviewed ee6dabb alone through `git show` and a `git archive ee6dabb` copy, not the working tree. That checkout is now at c1cc825, with another fork's uncommitted T-102 edits in manager.py, base.py and test_settings_sources.py. I did not touch them. Read-only on product code.

Both findings of reviews/T-101-f357434.claude.md are fixed.

Findings:
none

What was checked:
- Finding 1 (scope): fixed.
  - `_finish(tx, actor, e, facts, session_actor=None)` now passes `session_actor or actor` to `headless_session`.
  - Of its four callers, only `refuse` (executions.py:206) passes `session_actor`: the actor itself if it is system, otherwise `Ref('system', queries.system_principal(...))`. That code is inside the `discarded` branch, and states.py:193-194 has that edge only from PAUSED and AWAITING_APPROVAL.
  - `_ended` (:426, which serves `record_end` and `lost`), `record_handoff` (:685) and `approval_answered` (:717) call `_finish` without it. So `sessions._core` again refuses a non-Core actor on each of those paths.
  - Who calls `refuse` with a non-system actor: only `stop` (from `stop_execution`/`stop_mission`, which go through `_user`, and from `estop`, which allows user_device or system). Every other caller is the manager, `prepare_process` or `resume_checked`, and grep shows no route exposes them.
  - If no system principal exists, it still fails closed (`Ref('system', None)` at insert), as before.
- Finding 2 (tests): fixed.
  - `_ended_by` asserts that `execution.ended` and the `execution.state_changed` to ENDED_KILLED are exactly `('user_device', user.id)`, once each.
  - `_session_of` asserts that every event whose subject is the session is `system`, with exactly one `session.created`.
  - The e-stop test asserts that `core.estopped` has subject id and actor id equal to the user's, with kind user_device.
  - New tests: a PAUSED user stop (E20's pause, collected, `process_seq` 1, no session), `stop_mission` over an execution waiting for approval, and a user `record_end` on a RUNNING execution, which raises NotPermitted and leaves the event head and state unchanged.
- PAUSED and stop_mission tests are real: on b2dbf4c's executions.py both fail with "NotPermitted: only Core records what it observed of a session" (sessions.py:38).
- Claimed mutants are meaningful and each is caught:
  - The switch left in `_finish` (f357434's executions.py) fails the record_end test.
  - `refuse` ending as system fails all four stop tests at `_ended_by`.
  - `estop` stopping as system fails the e-stop test at `_ended_by`.

Observations (non-blocking):
- O1: the record_end test's `pytest.raises(NotPermitted)` has no `match=`, so it would also pass on an unrelated NotPermitted. M1 shows it catches the regression it is there for. A `match='only Core records'` would make that explicit.
- O2: `_session_of` checks that the actor kind is `system`. It does not check that the id is the engine's principal (`x.system.id`).
- O3: f357434's O1 (`checkpoint.derive` runs with the user's actor) is recorded on the card as left as is. That is fine.

Ran:
- `git -C D:/archeus-p20-mcp show ee6dabb` and `git diff b2dbf4c ee6dabb -- archeus/`. The only product change across T-101 is in executions.py.
- On a `git archive ee6dabb` copy (D:/trv-T101c-src, with `archeus.__file__` confirmed to point into the copy):
  - `py -m pytest tests/v1/integration/test_execution.py -k "stop or estop or record_end or paused" -p no:cacheprovider --basetemp=D:/trv-T101c`: 13 passed. This includes all 5 T101 tests, E21-E25, E30, E31 and E49.
  - `-k T101`: 5 passed.
  - The whole test_execution.py with `-m "not real_process"`: 63 passed.
- Mutants on the copy (scratch script; executions.py restored byte-identical and checked by sha256 and cmp against `git show ee6dabb:`):
  - M0, b2dbf4c's executions.py: 4 of 5 T101 tests fail, all with the exact NotPermitted. The record_end test passes, as it should.
  - M1, f357434's executions.py: only the record_end test fails.
  - M2, refuse ending as system: 4 tests fail at `_ended_by` (actor `system` where `user_device` is expected).
  - M3, estop stopping as system: the e-stop test fails at `_ended_by`.
  - M4 (mine), `core.estopped` recorded as system: the e-stop test fails at the estopped actor assert.
  - M5 (mine), refuse passing no `session_actor`: 4 tests fail.
- Scratch probes on the copy, deleted after:
  - A user `lost` on a RUNNING execution raises NotPermitted, with the head and state unchanged.
  - A user `approval_answered` after a reject raises NotPermitted, with the head unchanged. Core's own call then reaches ENDED_REJECTED with a session.
  - Core's own `refuse` of an execution waiting for approval ends it with `execution.ended` as system.
  - Under f357434's executions.py, the `lost` and `approval_answered` probes fail with "DID NOT RAISE". So the guard is restored by ee6dabb, not merely present.
- `py -m ruff check` on both changed files: all checks passed. `git show ee6dabb --check`: clean. CR count in the diff: 0.
- D:/trv-T101c and D:/trv-T101c-src were deleted.

Not checked:
- `record_handoff` with a user actor: by reading only, since it is the same `_finish(tx, actor, ...)` call and I wrote no probe for it.
- The card's other suites (test_settings_sources, test_estop_drills, judge test_g05_estop), the full tests/v1, POSIX, the real Claude CLI, the isolated path, and the route/SPA-level e-stop (tests/v1/e2e).
- c1cc825 and the uncommitted T-102 work in the checkout.

Reviewer: independent Claude agent (general-purpose), 2026-10-15
