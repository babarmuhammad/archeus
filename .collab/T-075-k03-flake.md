# T-075 · The transient k03 http-binding failures T-069 saw once

Claude (fork), 2026-10-14. Test runs and reading only. No product or test file was edited and nothing was committed.

## Result

**Not reproduced in 5 combined-set runs, 4 judge runs and 40 k03 runs.** No run failed `test_k03_project_setup`, on either binding or on either tree. T-069's fork didn't keep the failing output, so the failing assertion is unknown.

## What ran

All runs below used `-p no:cacheprovider`. Unless noted, they ran in `D:/archeus-pv20-k03` at cece71d (T-069).

| # | What | Conditions | Result |
|---|---|---|---|
| 1 | T-069's combined set (the 23 paths on its card) | alone, default basetemp | 719 passed, 11 skipped, 2 xfailed |
| 2, 3 | same set | two runs at once, basetemp under the session scratchpad (~120 chars) | **51 failed each**, the same 51 in both; none is k03 (see "Side finding") |
| 4, 5 | same set | two runs at once, short basetemps `D:/t075a`, `D:/t075b` | 719 passed, 11 skipped, 2 xfailed each |
| 6–8 | `tests/v1/judge` | three runs at once | 194 passed, 10 skipped, 2 xfailed each |
| 9 | `test_k03_project_setup.py` (4 tests × 2 bindings) | 25 times in a row, while runs 6–8 were going | 25/25 passed |
| 10 | `tests/v1/judge` in `D:/archeus-pv20-s2-l` (5dfac53) | alongside run 11 | 194 passed, 10 skipped, 2 xfailed |
| 11 | k03 in `D:/archeus-pv20-s2-l` (5dfac53) | 15 times in a row | 15/15 passed |

- **Orderings:** neither pytest-randomly nor xdist is installed. Orderings varied through file order: k03 inside the full alphabetical judge run, k03 after the unit and integration files in the combined set, and k03 alone, repeated.
- **`D:/archeus-pv20-s2-l`:** `git status --short` was identical before and after. The one entry, `?? tests/v1/integration/test_pv20_writer_fixture.py`, was there before I started.

## Does it predate T-069

Unknown. It reproduced on neither tree, and the two trees behaved the same.

Reading the diff points away from T-069: cece71d changes routing for the knowledge pass on **both** bindings. `FakeCaller` declares `no_tools` by default, and `GatedCaller` inherits it (`tests/v1/judge/conftest.py:77`, `archeus/harnesses/fake.py`). A cause in T-069's change would fail the inprocess cases too, and the report said only the http ones failed.

## What the code allows (most likely causes, unproven)

- **The http binding is the same Core, in-process, on a real socket.** `TempCore.start` runs `runtime.Core(port=…)` in this process (`tests/v1/judge/http.py:621-623`). Its callers are the test's own `FakeCaller` objects, so the binding differs from inprocess only in HTTP transport and timing.
- **Load is the leading candidate.** The http binding adds two clocks the inprocess one lacks:
  - every judge request has a **15 s socket timeout** (`http.py:77`, `request(..., timeout=15)`; `http.py:87`);
  - `wait_for` has a **30 s deadline** (`tests/v1/judge/support.py:82-97`), which `knowledge_pass` uses (`support.py:152-160`).

  When T-069's first combined run happened, at least three other forks were running mutation suites and pytest runs on this machine (T-060, T-061, T-066, per their reports of that hour). CPU starvation past either clock fails exactly the binding that has the clock.
- **Port reuse is ruled out as an assertion failure.** `free_port()` (`http.py:60-66`) has a close-then-bind window, but `Server` binds with `SO_EXCLUSIVEADDRUSE` on Windows and no `SO_REUSEADDR` (`archeus/api/server.py:409-421`). A clash would raise at `TempCore.start`, which is a setup ERROR, not a failed assertion. T-069's report says "failed", but a `-q` summary lists errors separately and the output wasn't kept, so this isn't fully excluded either.
- **No idle race found.** `_idle` (`http.py:138-157`) requires every worker idle with nothing pending, plus no unread event after the engine's and exec's observed sequence. `wait_for` re-reads the state once after `idle()` before giving up (`support.py:89-94`). I didn't find a window where k03's knowledge pass is neither visible nor counted as pending.

## Proposed card (instead of a fix)

There's nothing to fix until a failure is captured, so the card is about keeping the evidence:

- **Title:** Judge http failures keep their evidence.
- **Files:** `tests/v1/judge/support.py` (`wait_for`), `tests/v1/judge/http.py` (`request`).
- **Accept:**
  - On timeout, `wait_for`'s message names the elapsed time and the last value read.
  - A socket timeout in `request` re-raises with the method, path and elapsed time.
  - No timeout value changes.
- **Verify:** a fake-clock unit test for each message.

With that in place, the next flake says which clock fired. Owner's call whether it's worth a card. Without one, this stays "not reproduced".

## Side finding (out of scope, recorded only)

**`tests/v1/integration/test_verification.py` and the verification judge scenarios fail when pytest's basetemp is long.**

- **Runs 2 and 3:** 51 failures with basetemp `C:/Users/mab/AppData/Local/Temp/claude/D--Claude/<session>/scratchpad/k03/bt2`, giving an `archeus_home` of about 149 characters. Every one failed with `AssertionError: Core went idle before the awaited state`.
- **Single test:** `test_V09_forged_evidence_is_refused` alone fails under that long basetemp and passes under the default basetemp and under `D:/t075bt`.

This is consistent with a Windows `MAX_PATH` limit, somewhere under `worktrees/`, being hit and swallowed, so verification never starts. I didn't trace which call. It doesn't affect CI, whose basetemps are short, but an `ARCHEUS_HOME` deep enough would hit the same limit for a real user. That would be its own card: find the swallowed path-length failure and make it a visible refusal.

## Left behind

- My pytest basetemp folders `D:/t075a`, `D:/t075b`, `D:/t075bt`, `D:/t075ja`, `D:/t075jb`, `D:/t075jc`, `D:/t075k`, `D:/t075s`, `D:/t075sk`. The guard hook blocked `rm -rf`, so I didn't delete them; the owner can remove them.
- The run logs in the session scratchpad, under `scratchpad/k03/`.
- No checkout was modified.
