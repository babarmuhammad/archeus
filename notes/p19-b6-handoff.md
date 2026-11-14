# P19 B6 handoff — mission confirmation under `careful` (work in progress, uncommitted)

Branch `archeus-v1-rearchitecture`. Last commit: `ee97440` P19 B5 (chat approve / reject),
mutants P31-P40 10/10 killed, full suite 2478 passed with 3 failures, none of them B5's:
`test_one_name_per_command`, since fixed, and two intermittent e2e tests recorded in gate §12
item 22. **B6 is applied in the working tree and NOT committed.** Stopped at the user's request.

The working tree also holds edits from ANOTHER session: ADR-0007/0037/0042/0047/0049-0052, V2
assistant layer, XR-14 brief, external research, domain-model, execution-architecture,
orchestration docs, `.gitignore`, `.agents/`, `.codex/`, `notes/p16|p18|p19-5-*`. Do not stage
them with B6. Stage B6's files by name.

## What B6 does (as the gate approved: a P9 approval, no new route or edge)

- `mission.start` is a new action class, held in `actions.CORE_CLASSES`. `RULE_CLASSES` is
  `ACTION_CLASSES + CORE_CLASSES`. A rule and a judged Action may name it. A task never may:
  the planner, the validator and `Task` still read `ACTION_CLASSES`.
- Profiles: `standard` and `autonomous` ALLOW it, `careful` ASKs. `PROFILES_VERSION` is now 2,
  so the profile rule ids are `@2`.
- Approval kind `start`. It binds to the mission alone: `action_hash` accepts a binding with
  only `mission_id` for `start`. `TTL['start']` is 24h. Its presentation is `_presented_start`,
  scope "starting this mission".
- `authorization.gate_start` (also an `Authorization` method). The engine calls it in place of
  firing START on a CREATED mission. It handles the three decisions this way:
  - ALLOW fires START.
  - ASK records the `asked` decision once (stage `start`, added to `POLICY_STAGES`), requests
    the approval once (which posts B5's card), and the mission waits.
  - DENY (a user's rule) waits and records nothing.
- `judge_start` forces `estop=False`. Today's engine starts a CREATED mission while disarmed,
  and B6 keeps that. **This needs the user's review in §12.**
- `decide` / `_approve` / `ineligible` handle `start`:
  - Approving re-judges the start, then fires START.
  - Rejecting cancels the mission through `missions.cancel`.
  - Eligibility means the mission is still CREATED.
- `FixedPolicy` (stub) answers ALLOW for `CORE_CLASSES` unless `by_class` names one. Without
  this, every test using `FixedPolicy('ASK'/'DENY')` would stall in CREATED.
- Migration `0014_start_approvals.sql` rebuilds `approvals` with `plan_id` nullable.
  `test_db_schema` now expects 14. This departs from gate §6, which said "no schema": record it.
- Clients: the TUI Control matrix and Simulate field, and the SPA `Control.tsx` (`classesOf`),
  now derive the class list from Core's `profiles` instead of a hand copy. `generated.ts`,
  `_api.py` and `api-reference.md` are regenerated (the rule enum now includes `mission.start`).

## Verified so far

- `tests/v1/integration/test_start_confirmation.py`: 9/9. The cases are:
  - each allowing profile starts
  - careful waits, asks once, and posts the card
  - approve, then the plan asks
  - reject cancels
  - the chat card approves
  - cancelled while waiting
  - wrong hash
  - the e-stop doesn't hold a start
  - a DENY rule holds it without asking
- `test_policy_units.py`: pins moved to `@2`, builtin classes == `RULE_CLASSES`, and U_P3
  exempts `mission.start` from "never a bare ALLOW".
- `tsc` is clean, SPA unit tests 220/220, the SPA is built, and `gen_api_docs --check` is current.
- A background run of tui + unit + policy + schema + contract was in flight at handoff
  (task `b2v4oevrv`). Its result is not recorded here. Re-run.

## Still to do for B6

1. Run the full suite under a hidden console:
   `Start-Process py -ArgumentList '-m','pytest','-q','-p','no:cacheprovider','tests/v1' -WindowStyle Hidden ...`.
   Expect fallout wherever a test pins the profile ids, `POLICY_STAGES`, `APPROVAL_KINDS` or
   the schema version.
2. Mutants P41+ in `tools/mutate_p19.py` (constants `AUTHZ`, `CONV` and others already exist).
   Candidates:
   - careful ALLOWs `mission.start`
   - the engine fires START without `gate_start`
   - ASK requests a new approval every pass (drop the `live_approval` check)
   - approving does not fire START
   - rejecting does not cancel
   - `ineligible` ignores the mission having left CREATED
   - the e-stop holds a start (drop `estop=False`)
   - a DENY asks
   - `FixedPolicy` stops exempting `CORE_CLASSES`

   Check anchors occur once, as `mutate_p19.py`'s runner requires.
3. Docs:
   - Gate §12, "Slice 4b (B6)": the migration (a deviation from §6), `PROFILES_VERSION` 2, the
     e-stop choice, `CORE_CLASSES`, and the clients deriving the class list.
   - `testing-strategy`: the S4 row, if there is one.
   - `domain-model` §9: the approval kinds and the stages. That file also has the other
     session's uncommitted hunk, so stage only B6's hunk, via `git apply --cached` of a
     filtered diff.
4. Commit as "P19 B6: ...".

After B6, the gate's §5 order continues: B10, B4, B9, B7, B8, B12.

## Gotchas met this session

- The Bash heredoc eats `\n` in patch scripts (twice again). Write scripts with the Write tool
  and run them by path. The scratchpad scripts `b6.py`, `b6b.py` and `b6c.py` are already
  applied: do not re-run them.
- Cancelling a mission is the grammar's `cancel` (bare, in its thread). `/v1/missions/{id}/stop`
  only stops executions.
- A decided approval answers `422 invalid_transition`, not 409.
