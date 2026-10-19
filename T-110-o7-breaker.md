# T-110 · O7 backoff/breaker: what the canonical design says

Byline: **Qwen** (pi · spark/qwen3.8-flash-next), 2026-10-19. Card: `.collab/QWEN-CARD-T-110.md`.
Read-only analysis for T-106. Code read at `D:/archeus-p20-mcp` `git show b73f875:<path>`
(HEAD == b73f875, working tree clean); docs read in `D:/Claude/docs/architecture/` and
`D:/Claude/PV20-S1-GATE-2026-10-08.md`. No code written, no tests run, no process started, no
native/ACL operation, no web fetch.

---

## 1. Where O7 is recorded, and its exact words

**The decision itself** — `PV20-S1-GATE-2026-10-08.md` §7 "Gate re-evaluation — O7 resolved
(2026-10-08)", heading at line 128, decision line at 130, verbatim bullets at **lines 132–141**:

> - An isolation-establishment failure (`SpawnFailed`) is an infrastructure/isolation failure,
>   not a failure of the user's task.
> - It is therefore NOT charged against the task/execution outcome as task failure.
> - Retry is permitted only under a bounded backoff policy.
> - A breaker must prevent indefinite repeated attempts when isolation establishment is unhealthy.
> - After the retry/breaker policy is exhausted, the condition is surfaced as an
>   infrastructure/isolation failure requiring recovery/reconciliation.
> - There is NEVER an unisolated fallback.
> - There is NEVER a bypass of A4/isolation to make the execution run.
> - The failure state must remain deterministically reconcilable by Core across restart.

Two placements inside the same document matter for T-106:

- §7.3 (**lines 157–164**): "The backoff/breaker **policy mechanism** consumes those facts on the
  **dispatch side (P11-owned, production dispatch E-gated)** and is **not** a new S1 component.
  *Re-gate trigger:* should the owner later assign the retry/breaker policy mechanism itself into
  S1, that is a scope change and re-enters this gate."
- §7.5 item 10 (**lines 181–183**): "**No permission to modify production dispatch**: the
  retry/breaker policy operates only where dispatch already exists; S1 dispatches nothing,
  production dispatch remains unauthorized, and enabling it stays E's."

**Where O7 was born / deferred (canonical, pre-decision):**
- `docs/architecture/p20-design-gate.md` §4.2 O7 row, **line 371**: the `SpawnFailed` ends
  `binding` (uncharged) and "re-dispatches every tick. Charged, uncharged with a backoff or
  breaker, or routed away from the harness?" — deferred to P11 (user, 2026-10-07).
- Same gate, §12 item 64, **lines 1250–1262** ("**O7, OPEN**"; the three options; "40 executions
  in 40 ticks, measured in slice E"; "It is P11's code, outside slice E's authority").
- Same gate, §12 item 72, **lines 1420–1429** ("O7, deferred to P11… the choice between charging,
  a backoff or breaker, and routing away from the harness is not made in P20").
- Same gate, open-questions table **line 2233** ("O7 (deferred) | P11's `SpawnFailed` re-dispatch
  loop: charge, backoff/breaker or routing (§12 item 72) | P11's follow-up; a live loop when a
  harness cannot spawn").
- `docs/architecture/p11-design-gate.md` **lines 1018–1022**: "**O7 stays P11's** … Charged,
  uncharged with a backoff or breaker, or routed away from the harness is **P11's open decision**,
  required before PV-20 is implemented (PV-20 §3.4). It is not decided here."
- `docs/architecture/p11-design-gate.md` **lines 1030–1031** (A1 amendment): a structural
  workspace impossibility is refused **before dispatch**, so it never reaches `SpawnFailed`;
  "**Only a transient workspace failure is O7's.**"
- `docs/architecture/pv20-execution-isolation-design.md` **lines 309–312** (R8, external P11
  dependency), **line 400** ("Isolation setup failure → fail closed, do not spawn (§3.4);
  charging is O7's"), **line 650**, **line 715** (O7 "still open, and required before
  implementation"), **line 894** (establishment invariant "implementation-blocked | O7 still open").
- `docs/architecture/decisions/ADR-0053.md` **line 66**, **lines 178–179** (R8), **line 220**,
  **line 430** — same delegation, and the invariant "whatever O7 decides, it never bypasses isolation".

**Status of the question:** the O7 *decision* exists (gate §7). What does **not** exist is the
policy the decision mandates: §7 names a bounded backoff and a breaker as requirements without
specifying them, and no such mechanism is built (confirmed below, §4).

---

## 2. What the design names, and what it leaves open

Named by the canonical texts:

| Attribute | Named? | Where |
|---|---|---|
| Charging | **Named** — uncharged for an isolation-establishment failure | gate §7 (line 134) |
| Side/location (coarse) | **Named** — "the dispatch side", P11-owned, E-gated, **not** an S1 component | gate §7.3 (lines 157–162) |
| Never-bypass invariant | **Named** — never an unisolated fallback, never an A4 bypass | gate §7 (lines 139–140); PV-20 §3.4/§6.3 via ADR-0053 line 66 |
| Reconcilability | **Named** — "deterministically reconcilable by Core across restart" | gate §7 (line 141) |
| Exhaustion behaviour (coarse) | **Named** — surfaced as an infrastructure/isolation failure "requiring recovery/reconciliation" | gate §7 (lines 137–138) |

**Not named — each is an owner question for T-106:**

1. **Breaker location/subject.** Which entity carries the breaker — the harness, the account, the
   node, the isolation authority, or Core globally? "Isolation establishment" is a per-execution
   event under a per-node authority; every existing breaker is keyed to something else (§3). The
   design says only "dispatch side". → *Owner question Q1: what is the breaker keyed on?*
2. **Threshold.** No number exists for O7. The nearest precedents are the execution breaker's
   `STORM = 5` in `STORM_WINDOW_S = 600` and `PERSIST = 2` (`executions.py:801`), the pairing
   breaker's `FAIL_LIMIT = 10` in `FAIL_WINDOW_S = 60` (`api/auth.py:209–210`), and P14's loop
   guard `SUSPEND_AFTER = 3` in `WINDOW_S = 3600` (`core/automation/matcher.py:26–27`). None is
   O7's. → *Owner question Q2: what count of isolation-establishment failures trips it?*
3. **Window.** No window is named for O7 (same three unrelated windows exist). → *Owner question
   Q3: over what interval is the count taken?*
4. **Backoff shape.** "Bounded backoff" is named, the shape is not — no ladder, no floor, no cap,
   no holder of the timer. Precedent for the idiom: P14's "a retry runs at the worker's next pass
   after its backoff … the backoff is a floor, not a schedule" (`p14-design-gate.md:461–462`). →
   *Owner question Q4: the backoff sequence, and who holds the timer (Core writer thread vs a
   per-execution `not-before` timestamp).*
5. **Reset / recovery.** The decision says the state must be "reconcilable by Core across restart"
   but names no recovery trigger, probe, or half-open path, and no one names who clears the
   breaker. Compare the execution breaker's automatic `cooldown_elapsed` and `probe_ok`
   (`executions.py:848–853`, `states.py:296–298`) and the pairing breaker's self-clearing window
   (`api/auth.py:234`). → *Owner question Q5: does recovery need a human action (the decision's
   "requiring recovery/reconciliation"), or is it automatic on a probe?*
6. **Visibility.** The decision requires the exhausted condition be "surfaced"; the design never
   says where. Existing surfaces it could be surfaced on: the execution's own record (its
   `stop_reason`/reason text), the mission (`_block` at `executions.py:545–548`, driven by the
   `BLOCKING` stop-reason list at `executions.py:40–42` and `refuse` at `:211–212`), the isolation
   record's `isolation_failed` state (`node/isolation.py:783–799`), and the account-health copy in
   the TUI (`cli/tui/_tables.py:216–223`). → *Owner question Q6: which surface — mission blocked
   awaiting the user, a Core-level halt/state, the TUI/API, the UI string?*
7. **Scope of the breaker vs scope of the decision.** O7 as decided covers **isolation-
   establishment** failures only (gate lines 132–134; `p11-design-gate.md:1030–1031`). The loop that
   is actually live today is a **non-isolated** `Popen` failure (§4 case B), which is not isolation
   establishment. → *Owner question Q7: is the non-isolated permanent-`Popen` loop also O7's, or is
   it charged like `SpawnWriteFailed`/`workspace` (the T-102 precedent, `base.py:267–271`,
   `manager.py:324–331`), or added to `BLOCKING`?*
8. **Where the open breaker blocks.** At the router (which today never routes to `OPEN`, and only
   routes `DEGRADED` as a fallback — `state-machines.md` §9, `core/routing/router.py:49,272`) or in
   the manager before the spawn. → *Owner question Q8: router or manager?*
9. **Authority boundary.** Any mechanism that operates on production dispatch is E's (gate §7.3,
   §7.5 item 10), and `PRODUCTION_DISPATCH_ENABLED` is False (`node/isolation.py:86–90`). →
   *Owner question Q9: is T-106 allowed to touch the dispatch path with the switch off (code
   built, E unenabled), and does that satisfy §7.3's re-gate trigger?*
10. **Restart-reconcilable retry state.** Gate §7 line 141 records that the failure state must be
    "deterministically reconcilable by Core across restart", but nothing says how the *retry policy*
    state survives a restart: which counters, which backoff deadlines, and whether an OPEN breaker
    persist or are reconstructed from the isolation records, and whether a restart is allowed to
    replenish the retry budget (a crash-loop that resets the count defeats the breaker). The pairing
    breaker loses its `_fails`/`_locked_until` on restart (`auth.py:214–215`) — a counter-example,
    not an answer. → *Owner question Q10: which retry/breaker counters, deadlines and OPEN state
    survive or are reconstructed across restart, and may a restart replenish the retry budget?*

## 2b. Correction 2026-10-19 (Qwen) — reviews/T-110-analysis.md

Every Codex finding addressed in place; new/changed `file:line` per finding:

1. Open-questions table row re-cited to `p20-design-gate.md:2233` (was 2770; verified — that row is
   the only O7 "(deferred)" table entry at b73f875).
2. P14 backoff idiom re-cited to `p14-design-gate.md:461–462` (was 469–470; verified text "A retry
   runs at the worker's next pass after its backoff … the backoff is a floor, not a schedule").
3. §3.3 pairing unlock: now "monotonic clock" — `clock=time.monotonic` at `auth.py:212`, unlock
   check `now = self.clock()` / `now < self._locked_until` at `:223–225` (not wall clock).
4. §3.4: manual recovery demoted to a *candidate* model; the decision requires
   "recovery/reconciliation" but does not decide manual-vs-automatic — cross-referenced to open Q5.
5. §4 Case B step 4: removed "every pass"/"never" scheduling claims; conclusion kept as
   *indefinite, uncounted redispatch* (`manager.py:116–141`, `runtime.py:293–295`) rather than a
   guaranteed busy loop.
6. §4 Case C: `Isolation.requested()` claim qualified to a *fresh* production request; record check
   returns True first at `isolation.py:690–691`, production switch gates only new requests at
   `:694–695`.
7. Added owner question **Q10** (restart-reconcilable retry state: which counters/deadlines/OPEN
   survive or are reconstructed, and whether restart may replenish the retry budget); §5 updated.
8. §5 minimum decision set now includes Q4 (bounded backoff) and Q8 (enforcement location).


---

## 3. Existing breaker code that could carry it (all at b73f875)

### 3.1 Execution breaker — account health `AVAILABLE/CONSTRAINED → DEGRADED → OPEN`
- State machine: `archeus/core/domain/states.py:285–303` (`account_health`: `error_storm`,
  `errors_persist`, `probe_ok`, `cooldown_elapsed`).
- Driver: `archeus/core/application/executions.py:825–860` (`accounts_tick`), constants at
  `executions.py:799–801` (`BEAT_S = 60`, `STORM, STORM_WINDOW_S, PERSIST, COOLDOWN_S = 5, 600, 2,
  300`); called from `manager.tick()` at `manager.py:130–132` (`ACCOUNTS_S` cadence).
- Counts only `ENDED_ERROR` executions whose `failure` is `resource` or `auth`
  (`executions.py:838–843`) — an ABANDONED refusal (`manager.py:338–339`) is **not** an
  `ENDED_ERROR` and never reaches this counter.
- Canonical spec: `p11-design-gate.md` §12.4 (**lines 452–467**), `state-machines.md` §9
  (**line 579 ff.**); listed in `p20-design-gate.md` §1.6 (**lines 130–134**).
- **Fit:** the shape is right (thresholded failure count, one level per beat, cooldown, probe).
  The key is wrong — it is keyed on a registered Account and counts resource/auth ends. It could
  carry O7 only by (a) counting isolation/spawn failures too, which changes a canonical threshold
  contract (§12.4 "Counted: … `resource` … or `auth`. A task-attributable error never counts"), or
  (b) cloning the machine for a new subject (harness/isolation), which is the cleaner reading of
  gate §7.3's "dispatch side". Note `p11-design-gate.md:951`: a harness's own account (no
  registered Account) is charged precisely "because no breaker can see that account".

### 3.2 Harness state (a candidate key, not a breaker)
- `archeus/core/domain/states.py:395` — `'harness': ('AVAILABLE', 'MISSING', 'MISCONFIGURED')`,
  set by discovery only; no failure-driven transition exists.
- Router filters on the snapshot's harness fields, not on a health counter
  (`archeus/core/routing/router.py:100–110, 217, 272`).
- **Fit:** the natural subject for a "harness that cannot spawn" breaker (p20 item 64's third
  option, `p20-design-gate.md:1261`), but today it has no trip/reset moves at all — building on it
  means new canonical transitions.

### 3.3 Pairing breaker (`PairingLocked`)
- `archeus/api/auth.py:198–236` — `FAIL_LIMIT = 10`, `FAIL_WINDOW_S = 60.0` (`:209–210`); the
  count list `self._fails` (`:214`), trip → `_codes.clear()` + `_locked_until = now + 60`
  (`:231–235`), self-reset by the **monotonic** clock (`clock=time.monotonic` at `:212`; unlock
  checked against `self.clock()` at `:223–225`, not wall clock). `routes.py:274–276` maps it to `429
  pairing_locked`.
- **Fit:** the simplest in-process shape (sliding window + timed unlock, in memory), and the
  cheapest to imitate. It is not reconcilable across restart (`_fails` and `_locked_until` are
  in-memory, `auth.py:214–215`), so it violates gate §7's "deterministically reconcilable by Core
  across restart" (line 141) if copied verbatim for O7.

### 3.4 P14's automation loop guard
- `archeus/core/application/automations.py:269–279` (`_guard` → `loop_guard_tripped`), with
  `core/automation/matcher.py:26–27` (`SUSPEND_AFTER = 3`, `WINDOW_S = 3600`); transition
  `states.py:263` (`ENABLED → SUSPENDED`), surfaced in the TUI as `loop_guard_tripped`
  (`cli/tui/_tables.py:364`).
- **Fit:** the only existing mechanism whose *exhaustion* semantics match gate §7's "surfaced as an
  infrastructure/isolation failure requiring recovery": it **suspends until a user re-enables it**
  (`automations.py:276–278`). This is one *candidate* model for the recovery O7's lines 137–138
  leave open — the decision says the condition requires "recovery/reconciliation" but does **not**
  decide whether that recovery is manual or automatic (that is the open Q5 above).
  Its subject is an Automation, and its count is of escalated/rate-limited runs, so again it is a
  pattern to copy, not a counter to reuse.

### 3.5 The mechanism that already stops this class of loop (no breaker needed)
- `BLOCKING = ('path_too_long',)` at `executions.py:40–42`, honoured by `refuse`
  (`executions.py:211–212` → `_block` at `:545–548`): a refusal every later attempt would repeat
  blocks the mission so the READY task is not re-dispatched until the user resumes it. Its docstring
  is the exact anti-loop intent. Adding an O7 stop reason to `BLOCKING` is a one-line mechanism that
  already exists, is charged-neutral, and is user-visible — but it is a *halt*, not a *bounded
  retry*, so it only answers the "after the policy is exhausted" clause (gate lines 137–138), not
  lines 135–136.

---

## 4. The dispatch path a permanent spawn failure takes today (b73f875), and why it loops

Entry: `ExecLoop._run` → `manager.tick()` (`core/runtime.py:286–295`, `EXEC_S = 0.05` at `:260`) →
`manager._step` (`manager.py:170–188`) → `_first` (`:192–203`) → `_spawn` (`manager.py:205–348`).

Three distinct permanent-failure shapes today:

**Case A — a pre-child write Core could not make (already bounded, T-102):**
`base._start` writes class dirs/marker/prompt → `OSError` → `_refuse(..., SpawnWriteFailed)`
(`harnesses/base.py:341–363`, class at `:267–271`) → `manager._spawn` catches
`base.SpawnWriteFailed` and refuses with the **charged** `stop_reason='workspace'`
(`manager.py:324–331`). Charged → `charged_failure` counts attempts → the task ends FAILED after
`max_attempts` (`executions.py:484–499`, `charged_attempts` at `:69–72`). **No loop.**

**Case B — the permanent `Popen` failure (the live loop, the one the review measured):**
non-isolated path: `proc.spawn_detached(...)` returns `(None, err)` (`base.py:390–392`) → `child is
None` → `_refuse(paths, err, None)` (`base.py:393–396`) → writes the `ended` tombstone and raises
`SpawnFailed` (`base.py:400–408`) → `manager._spawn` catches `(base.SpawnFailed, base.AlreadySpawned)`
and refuses with **`stop_reason='binding'`** (`manager.py:332–341`), then `_release_isolation(e)`.

Why it loops, step by step:
1. `binding` ∈ `UNCHARGED` (`executions.py:38–39`), so `refuse` writes `charged: False`
   (`executions.py:195`) and fires `spawn_failed` on an INTENT execution (`:198–200`) → ABANDONED.
2. `_respond` sees `e.charged is False` and fires `execution_failed_retry` unconditionally
   (`executions.py:480–483`) — **`max_attempts` is never consulted on that branch** (it is only
   consulted in the charged branch, `charged_failure`, `:490–499`). The task returns to READY.
3. `binding` ∉ `BLOCKING` (`executions.py:40–42`), so nothing blocks the mission; `EngineLoop`
   re-dispatches the READY task (`core/runtime.py:158–167`; `core/engine.py:272–280` →
   `work.dispatch_task`, `core/application/work.py:315–330`) and a new INTENT execution is committed.
4. A tick that finds work returns nonzero `did` (`manager.py:116–141`), so *that* tick skips
   `ExecLoop`'s `EXEC_S` idle wait (`runtime.py:293–295`); the dispatch→refuse→re-dispatch cycle
   keeps handing work back, so the redispatch is **indefinite and uncounted** — nothing in this path
   counts, delays, dedupes or bounds it. (The defect is the absence of a bound, not a guaranteed
   busy loop: any individual pass that finds nothing may still take the `EXEC_S` wait.) Each such
   pass writes an Execution row, its events, an exec dir, a marker and a tombstone.
5. The breaker cannot see it: `accounts_tick` counts only `ENDED_ERROR` + `failure in ('resource',
   'auth')` (`executions.py:838–843`); an ABANDONED refusal is neither.
   Measured independently (review `reviews/T-102-c91d4f1.claude.md`, "Ran"): **63 uncharged
   ABANDONED executions in 4 s** with a permanent `Popen` failure; canonical: "40 executions in 40
   ticks" (`p20-design-gate.md:1255–1256, 1425–1426`).

**Case C — a genuine isolation-establishment failure (O7's own scope, latent):**
isolated path: `_private_dirs`/`_isolated_env` failures → `_refuse` → `SpawnFailed`
(`base.py:364–376`); `IsolationContext.launch` converts `IsolationUnavailable` to
`base.SpawnFailed` (`node/isolation.py:1567–1602`, raises at `:1577`, `:1600`, `:1602`);
`LocalNode.spawn` records the deterministic state via `isolation.note_failure` before re-raising
(`node/local.py:164–172`; `isolation.py:783–799` writes `state: 'isolation_failed'`), then
`manager.py:332–341` refuses it as uncharged `binding`. This is exactly the case the O7 decision
calls uncharged — and it is **not reachable in production today**: `Isolation.requested()` returns
False **for a fresh production isolation request** while `PRODUCTION_DISPATCH_ENABLED` is False
(`isolation.py:685–696`: the production switch gates only new requests at `:694–695`; an execution
that already has a record returns True first at `:690–691`, so the disabled switch is *not* a
universal False for `requested()`), and `default_plan` is deliberately unsatisfiable for production
(`isolation.py:1524–1534`).
So: the case O7 was written for is latent; the case actually looping is Case B. That is owner
question Q7 above.

**No mechanism of O7 exists in the tree at b73f875:** `git grep` for `backoff` finds none in
`archeus/core/execution/`, `archeus/harnesses/`, `archeus/node/`; the only breaker drivers are
`accounts_tick` (`executions.py:825–860`) and the pairing/automation guards of §3. The comment at
`manager.py:336–337` points at "the bounded retry policy that policy owns" — that policy does not
exist yet, which matches `reviews/T-102-c91d4f1.claude.md`: "No such mechanism exists yet."

---

## 5. What this feeds into T-106

- T-106 can be built once the owner answers Q1–Q10 (§2). Nothing in the canonical texts blocks
  building it; §7.3/§7.5-10 place it on the dispatch side and keep production dispatch E's.
- Minimum owner-decision set for a first cut: Q1 (key), Q2+Q3 (threshold+window), Q4 (bounded
  backoff shape/timer holder), Q5 (recovery), Q6 (surface), Q7 (does Case B belong to O7 or is it
  charged like `workspace`), Q8 (enforcement location — router or manager), Q10 (restart-reconcilable
  retry state). Q9 (authority boundary) gates *where* it may be built, not whether it can exist.
- Non-negotiables the implementation must keep, with their sources: no charging the task
  (gate §7 line 134), no unisolated fallback and no A4 bypass (lines 139–140; PV-20 §3.4/§6.3 via
  ADR-0053:66), restart-reconcilable state (line 141), no new S1 component / no enabling of
  production dispatch (gate §7.3, §7.5 item 10; `isolation.py:86` stays False), and the S1 gate's
  ACL rule (no grant path returns; `test_pv20_isolation.py`'s static gate).

## 6. Provenance and limits of this analysis

- Read: the files and line ranges cited above, `git show b73f875:<path>` for code; docs read from
  `D:/Claude` working tree (canonical documents, unmodified here).
- Not run: any test, any process, any probe, any native/ACL call, any web fetch. The "63 in 4 s"
  and "40 in 40 ticks" numbers are quoted, not re-measured.
- No conflict between canonical documents was found: p20 §4.2/§12, p11 §12.4/notes, PV-20 §3.x/§7
  and ADR-0053 all delegate O7 the same way, and the gate §7 decision is consistent with them
  ("uncharged is a legal value of that delegation", gate §7.2, lines 152–155). So per the card's
  `review:` line this goes to the independent Claude reviewer, not Codex.
