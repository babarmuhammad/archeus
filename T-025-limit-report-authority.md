# T-025: provider-limit report authority and its lifecycle consequences

Card T-025, analysis only. This note was written by reading code and contracts. It runs no tests, no provider or model calls, no native calls and no real CLI. All code citations are to the S2 worktree at `efc31cc` (taken with `git show efc31cc:<path>`), so they stay stable while T-023 and the T-024 correction land. All doc citations are to the same commit.

## 1. Sources

- **Code:**
  - `archeus/harnesses/claude_code/adapter.py`: `normalise` 76-77; `status` 194-209; `collect_result` 222-241.
  - `archeus/harnesses/fake.py` 171-178.
  - `archeus/core/execution/manager.py`:
    - `_NOW` 51
    - `_watch` 357-368
    - `_tail` limit branch 384-389
    - `_control` 457-493
    - `_collect` 499-547
    - `_stop_account` 597-611
    - `_ceilings` 622-631
    - `_reconcile_isolated` 717-756
    - `_collect_gone` 814-831
  - `archeus/core/application/executions.py`:
    - `UNCHARGED` 38
    - `record_end` 221-282
    - `_respond` 342-362
    - `HANDOFF_CAUSES`/`request_handoff` 475-487
    - `record_handoff` 528-567
    - `account_limited` 679-688
    - breaker 691-726, with the failure filter at 706
  - `archeus/core/application/resources.py` `_affinity` 396-411.
  - `archeus/node/local.py` `kill` 121-130.
  - `archeus/core/routing/usage.py` `LegacyUsageFeed` 53-69.
  - `claude_sessions/quota.py` `is_limit_error` 361-363.
- **Contracts:**
  - `pv20-execution-isolation-design.md`:
    - §3.3 table row 212
    - stream content as a claim 216-219
    - H2 221-232
    - A7 233-242
    - §6 items 16 (595-597) and 24 (634-639)
  - `state-machines.md` PV-20 correction 369-381.
  - `p11-design-gate.md`: §8.3 table 255; §12.3 443-450; D22 868.
  - `p12-design-gate.md` §10.1 296-319.

## 2. The path a limit report takes

1. **The claim.** The Claude Code adapter emits `{'type': 'limit', 'window', 'text'}` for a stream-json `result` line that has `is_error` set and whose text matches `quota.is_limit_error` (adapter 76-77). The event has no `resets_at`. `collect_result` sets `failure = 'limit'` if any `limit` event appears anywhere in the stream (230-231).

   This is the execution's stream content. PV-20 calls it "execution-authored even though Core holds its handle: a `result` in it is a claim, never a process exit" (pv20 216-219).

   The fake harness also turns `{'type': 'error', 'error': 'rate_limit'}` into `failure = 'limit'` at collection only (fake.py 176-178). That is why the exit-time branch below exists (p12 §21, S4.3).

2. **Stream time: `_tail`, manager 384-389.** This runs once per process, guarded by `p['limit']`, and only when `e.account_id is not None`:
   - Core records progress, which moves a STARTING execution to RUNNING.
   - It fires `account_limited` with `resets_at=ev.get('resets_at')`. That value is always `None` for Claude Code, so the account goes LIMITED until now + `LIMIT_DEFAULT_S` = 3600 s (executions 683). The move happens only from AVAILABLE or CONSTRAINED (684).
   - It calls `_stop_account(account_id, 'limit', …)`.

   `_tail` also runs first inside `_collect` (501). A limit first read after the process has exited therefore takes this same branch, with no kill.

3. **The fan-out: `_stop_account`, manager 597-611.** This covers every live execution on that account, across all missions, not only the reporter:
   - A RUNNING one gets `request_handoff(stop_reason='limit')` and moves to HANDING_OFF (604-607).
   - A STARTING, PAUSING, INTENT, PAUSED or AWAITING_APPROVAL one gets `X.stop(stop_reason='limit')` (609).

4. **The kill: `_control`, manager 480-484.** `'limit'` is in `_NOW` (51), so a HANDING_OFF execution is killed at once. In `_watch` this happens in the same pass, because `_control` (365) runs after `_tail` (357).
   - If the process is still alive, `LocalNode.kill` calls `adapter.stop`. The adapter records the id in `_stopped`, and `collect_result` then reports `exit_reason='killed'` (adapter 235).
   - If the process has already exited, `kill` returns `'gone'` and nothing is marked (local 124-125).

5. **The exit-time backstop: `_collect`, manager 515-521.** This fires only if the execution is still RUNNING with `result.failure == 'limit'`. Two cases reach it:
   - the fake's `error`/`rate_limit` wording;
   - a restart where the limit line lies before `stream_offset`, so `_tail` does not see it again.

   It fires `account_limited` (again without `resets_at`) and `request_handoff('limit')`. It does not kill anything, because the process has already gone.

6. **Classification: `_collect`, manager 522-543.**
   - Ordinary execution: a hand-off if `exit != 0 or result.halted or killed`.
   - Isolated execution (T-022): a hand-off only if `exit == 0 and not killed`.
   - A HANDING_OFF hand-off goes to `record_handoff`: ENDED_HANDOFF, uncharged unless the ADR-0047 no-progress guard fires, plus a continuation through P9/P10 (executions 528-567).
   - Every other end goes to `record_end`.

7. **Charge in `record_end`.** The non-STOPPING path (270-282) computes:
   - `uncharged = failure in ('resource','auth') and account_id`
   - `stop = 'limit' if failure == 'limit' and account_id`
   - `charged = not (uncharged or stop)`

   The execution's own `stop_reason` is kept (`stop or e.stop_reason`) but is **not consulted for the charge**, so a `stop_reason` in `UNCHARGED` does not make this path uncharged. The STOPPING path (256-260) does consult it: `charged = e.stop_reason not in UNCHARGED`.

8. **Downstream effects.**
   - `_respond`: an uncharged end takes `execution_failed_retry` to READY (355-358). A charged one goes through `charged_failure` (359-361), which retries or FAILs once the budget is spent.
   - `_affinity` drops the route of any execution whose `stop_reason` is in `('ceiling', 'limit', 'breaker')`, whatever its end state (resources 400-404).
   - The breaker counts only ENDED_ERROR ends with `failure in ('resource','auth')` (706), so a limit end never feeds it, on either path.

## 3. What Core observed and what the report claimed

**What Core observes:**
- The exit code from the process handle it holds: `Popen.poll`, or `GetExitCodeProcess` for an isolated child.
- An `ended` tombstone it wrote itself.
- Its own kill, the `_stopped` set.
- Its own state: the state machine, `stop_reason` and `p['limit']`.

**What the execution claims:**
- That the provider refused for a limit (the `result` text and `is_error`).
- Whether that refusal names a window (`window`, which Core computes and never reads).
- The `result` subtype and summary.

**What Core does with the claim:**
- It sets **Core-authored state**: the account becomes LIMITED for an hour.
- It hands off or stops **other executions**, including ones in other missions.
- It decides the reporter's **charge**: uncharged on a registered account, through `failure == 'limit'`.
- It drops route **affinity**.

## 4. Matrix A: the reporting execution (registered account)

Every row of Matrix A shares four effects:
- The account goes LIMITED for 3600 s, from AVAILABLE or CONSTRAINED, once per process.
- The breaker is not affected.
- Affinity is dropped, because `stop_reason` is `'limit'`.
- `stop_reason` is `'limit'`.

| Case | Core observed | Ordinary result (`p11`/`p12` as built) | Isolated result (T-022) |
|---|---|---|---|
| A1: limit read while alive, then Core's kill | killed (own kill), non-zero code | ENDED_HANDOFF, uncharged, continuation (p12 §10.1 steps 2-3) | ENDED_ERROR, **uncharged** (`failure='limit'`), no continuation; task READY through ordinary retry |
| A2: exited on its own before the kill, or limit first read at collection; exit 0 | exit 0, not killed | `record_end`: ENDED_OK, uncharged (`stop='limit'`), task to VERIFYING | ENDED_HANDOFF, uncharged, continuation |
| A3: as A2, exit non-zero | exit ≠ 0 | ENDED_HANDOFF, uncharged, continuation | ENDED_ERROR, uncharged, no continuation; task READY |
| A4: as A2, exit unreadable (`None`) | no code | ENDED_HANDOFF, uncharged, continuation | ENDED_ERROR, uncharged, no continuation |
| A5: Core restart while HANDING_OFF | nothing; isolated: own kill by identity (`_reconcile_isolated` 731-734) | `_collect_gone` uses exit `None` (820-822): ENDED_HANDOFF, continuation | `record_end(exit None, killed=True)` with **no `failure`** (749-752): ENDED_ERROR, **charged**, `stop_reason='limit'` |

Notes on the matrix:
- **A1 versus A2 is a race.** Which one happens depends on whether the CLI writes its `result` line long enough before exiting for a `_watch` pass to read it while the process is alive.
- **A2 ordinary is existing behaviour:** a limit refusal with exit 0 becomes ENDED_OK, and only verification stops it from becoming success. Whether the CLI exits 0 on a limit is unverified (§8).
- **The isolated path never reaches ENDED_OK from a limit report.** That conforms to A7.
- **No-continuation consequence (A1, A3, A4).** In these isolated rows the work does not continue as a hand-off. A fresh retry re-routes the task, and the LIMITED account is not eligible. The retry prompt does not carry the checkpoint rendering, because p12 §10.1 step 5 applies to continuations only. A checkpoint is still derived by `_finish` (296-297).

## 5. Matrix B: other executions on the same account (no report of their own)

| Sibling's state when the reporter's limit is read | Ordinary | Isolated |
|---|---|---|
| RUNNING: `request_handoff('limit')`, then an immediate kill | ENDED_HANDOFF, uncharged, continuation | ENDED_ERROR, `failure=None`, **charged**, `stop_reason='limit'`; the task spends an attempt, or FAILs if its budget is spent |
| STARTING or PAUSING: `X.stop('limit')`, then STOPPING, then a kill | ENDED_KILLED, uncharged (256-260) | same |
| INTENT, PAUSED or AWAITING_APPROVAL: `X.stop`, then `refuse` (387-389) | ended uncharged, no process | same |

## 6. Rows without a limit report, and the unregistered account

- **Same charge rule, no report.** An isolated HANDING_OFF for `pressure`, `ceiling` or `handoff_user` that Core kills after `pause_timeout` (483-484), or that a restart resolves (749-752), also ends ENDED_ERROR and **charged**. Its `stop_reason` is in `UNCHARGED`, but `record_end` does not consult it.
- **The cooperative case is the open question.** For an isolated hand-off that halts at a tool boundary, the outcome depends on the exit code of a halted CLI, which is unverified:
  - exit 0: ENDED_HANDOFF;
  - otherwise: ENDED_ERROR, charged.
- **Unregistered account** (`account_id None`, a harness's own account). There is no LIMITED and no hand-off; the end is classified as a RUNNING end:
  - exit 0: ENDED_OK, which moves the task to VERIFYING only;
  - non-zero or unknown: ENDED_ERROR, charged, as p11 §12.3 and D22 require.

  Ordinary and isolated behave the same here, apart from the existing `halted` rule for RUNNING ends.

## 7. What the existing architecture permits

**For the reporting execution's own classification.**
- H2 lets a report move "an execution's classification only toward a non-advancing state". It can never manufacture success, an approval, a response, a flag or any other Core-authored state (pv20 226-229). The PreCompact precedent: "a PreCompact report can only raise context pressure; Core decides any handoff" (229-230).
- A limit report used as an input to Core's own `request_handoff` fits the same pattern. HANDING_OFF, ENDED_HANDOFF, ENDED_ERROR and READY are all non-advancing.
- A7 (233-242, state-machines 377-381) is met on the isolated path:
  - exit 0 from HANDING_OFF goes to ENDED_HANDOFF;
  - a non-zero or unknown exit goes to ENDED_ERROR;
  - no row reaches ENDED_OK from HANDING_OFF.

**Beyond that execution, the contract is silent or in tension.**
1. **Account health is Core-authored state.** H2's "any other Core-authored state" could be read as covering the account's LIMITED. It could equally be read as allowing a non-advancing Core decision taken from a claim, as with pressure. Neither document addresses account state or other executions.
2. **Effects reach other executions, including other missions'.** The §3.3 table (212-214) makes halt and hand-off state "Core only — the execution cannot author it". Here one execution's claim causes Core to hand off, or under isolation to end, every other live execution on that account. Each effect is non-advancing, so this is a denial-of-service lever and not a privilege, but it crosses the execution boundary PV-20 draws.
3. **The report decides the reporter's own charge.** On a registered account a claimed limit makes the end uncharged (record_end 276), so a failing execution can avoid spending an attempt. This is bounded: each claim sets one account LIMITED for an hour and drops affinity, so the task runs out of eligible accounts and P10 blocks the mission. P11 D22 already accepts it for ordinary executions. H2 says nothing about charge.

**Charge on an isolated HANDING_OFF end has no contract behind it.**
- P11 §8.3 (255) and P12 §10.1 make a Core-initiated hand-off, limit stop or ceiling stop uncharged.
- Before T-022, `_collect` never reached HANDING_OFF → ENDED_ERROR on the ordinary path: a non-zero, unknown or killed end is always a hand-off there.
- So `record_end`'s RUNNING-oriented charge rule is now applied, for isolated executions only, to ends that Core itself caused (Matrix A5, Matrix B row 1, §6).
- Charging those ends is a change to attempt accounting that no card decided. It happens silently, and the T-022 tests do not assert the charge.

## 8. Unverified real-CLI behaviour (needs a separately authorized real-CLI run)

1. Does the Claude CLI under `-p --output-format stream-json` exit 0 or non-zero when the provider refuses for a session, weekly or rate limit? This decides between A2 and A3, and between ENDED_OK and a hand-off on the ordinary path.
2. Is the refusal emitted as a `result` line with `is_error: true` and the limit text? The evidence quoted in the product's own notes is from `--output-format json`.
   - The transcript's `"error": "rate_limit"` / `apiErrorStatus 429` wording also appears on `assistant` lines, which `normalise` ignores (adapter 56-78).
   - The CLI may retry a 429 internally and never report it.
3. How long after the `result` line does the process exit? This decides between A1 and A2.
4. What exit code does a CLI produce after the hook halts it at a tool boundary (`HANDOFF`/`PAUSE` flag)? This decides every cooperative isolated pause and hand-off (§6).
5. Does `LegacyUsageFeed`'s polled window percentage (usage.py 53-69) reflect the refusal the CLI reported, for each kind of limit?

## 9. Correction options, each needing a separately scoped card

**C1: charge for a Core-caused isolated HANDING_OFF end.** Recommended as the smallest correction.
- **Change:** in `record_end`, an end observed in HANDING_OFF whose `stop_reason` is in `UNCHARGED` takes `charged = False`, as the STOPPING path already does (259). This covers the limit, pressure, ceiling and user hand-offs that Core killed, timed out or resolved at restart.
- **What stays the same:** the state stays ENDED_ERROR with no continuation, exactly as A7 and T-022 require.
- **Files:** `executions.py`, plus charge assertions added to the T-022 `LIVE_ENDS` table in `test_execution_units.py`. The ordinary path is unaffected, because it never reaches that edge.
- **Gate:** it changes no state, no route, no A7 rule and no breaker input.
- **Alternatives:**
  - **(C1b)** Keep the charge only where `killed` is false, so a non-zero cooperative exit is still charged.
  - **(C1c)** Route a hand-off that Core killed to `record_handoff` (ENDED_HANDOFF with a continuation). This restores p12 §10.1 steps 2-3 for isolated executions. It **needs an A7 ruling**: A7's text sends a non-zero exit from HANDING_OFF to ENDED_ERROR, and Core's own kill produces a non-zero exit. It must not be done under T-022's approval.

**C2: the limit report's effect beyond the reporter.** No code is proposed without an owner ruling.
- **(C2a)** Keep the current behaviour and record it in PV-20 §3.3 as an accepted, non-advancing report effect (a DoS lever). This is documentation only.
- **(C2b)** For an isolated reporter, apply LIMITED and the account-wide fan-out only after a Core-side observation corroborates it, such as `LegacyUsageFeed` showing the window spent. The hand-off of the reporter alone stays.
  - **Risk:** a genuine limit the feed cannot see (a bare 429, a non-Claude harness, no `home_ref`) leaves the account AVAILABLE. Uncharged ends could then loop on that account. Pairing C2b with C3 bounds the loop.
  - Depends on §8 item 5.
- **(C2c)** Fan out only to the reporter's own mission. The cross-mission effect goes, but within the mission the lever remains.

**C3: the reporter's own charge under isolation.** No code without a ruling.
- **(C3a)** Keep P11 D22: a claimed limit on a registered account is uncharged.
- **(C3b)** For an isolated reporter, charge a claimed limit unless Core corroborates it. This changes D22 for isolated executions and must be decided explicitly, never slipped into another card.

**Observation, out of scope and not proposed.**
- `window` (`is_window_limit`) is computed and never used. A transient 429 therefore marks the account LIMITED for a full hour.
- Claude Code limit events never carry `resets_at`, so the reset time is always the one-hour default.

## 10. Owner questions

1. Should C1 go ahead as a separate card: an isolated HANDING_OFF end with a `stop_reason` in `UNCHARGED` is uncharged, and its state is unchanged? Or is charging Core-caused isolated hand-off ends intended?
2. If the charge is not enough, should A7 be read, or amended, so that a hand-off Core itself killed is "a cause Core can classify from its own state" and reaches ENDED_HANDOFF with a continuation (C1c)?
3. Does H2's "only toward a non-advancing state" cover a report's effect on **shared Core state** (account LIMITED) and on **other executions**, including other missions' (C2a)? Or is a report confined to its own execution (C2b, C2c)?
4. Under isolation, may an execution's own claim of a limit keep its end uncharged (C3a, P11 D22 as built), or must that need Core corroboration (C3b)?
5. Will you authorize the real-CLI evidence run in §8 (exit code on a limit refusal, its stream form, the exit-to-result timing, the exit code after a hook halt, usage-feed visibility)? Every isolated row above that depends on an exit code is unverified until that run.
6. Should the unused `window` distinction and the missing `resets_at` get their own card? This note proposes no change to them.
