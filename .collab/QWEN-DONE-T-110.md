STATUS: review

Card: T-110 · O7 backoff/breaker: what the canonical design says (code-and-doc analysis for T-106)
Owner of card: qwen · Byline: Qwen (pi · spark/qwen3.8-flash-next) · Date: 2026-10-19
Deliverable: `D:/Claude/.collab/T-110-o7-breaker.md` (new, 19,634 bytes) — read-only analysis, signed Qwen.
Card file updated: `D:/Claude/.collab/QWEN-CARD-T-110.md` (status → `review`, notes record what ran).

## Commits

**None.** The card's `scope:` is `.collab/T-110-o7-breaker.md` (new note) and the card itself, and
`.collab/` is excluded from git by `D:/Claude/.git/info/exclude` (line 20: `/.collab/`). Nothing
committed, nothing staged, nothing pushed. `commits:` on the card stays `-`.

Verified before writing this file:
- `git -C D:/archeus-p20-mcp status --porcelain` → **no output** (tree clean at `b73f875`, which is
  also its HEAD; `git rev-parse HEAD` = `b73f875f1e3eabc23afd8b006360390178708f16`).
- `git -C D:/Claude status --porcelain` → only the pre-existing entries that were there before this
  card (` M docs/design/ARCHEUS_V2_UI_ARCHITECTURE.md`, ` M docs/design/ARCHEUS_V2_UI_RESEARCH.md`,
  ` M docs/design/ARCHEUS_V2_VISUAL_DIRECTION.md`, untracked `.agents/`, `.codex/`, `.spike/`,
  `HANDOFF-*.md`, `PV20-S1-ACCEPTANCE-2026-10-09.md`). **No tracked file was changed by this card.**

## What ran, with exact results

Per `verify:` — "read-only grep and reading of D:/archeus-p20-mcp (git show b73f875:<path>); no
code, no tests, no process, no native or ACL operation, no web fetch." All of it was reads.

1. `git -C D:/archeus-p20-mcp log --oneline -3 b73f875` → `b73f875 PV-20 T-102: an end and the boot
   sweep also remove the MCP config's temp copy` (parent `0fb5daa`, then `fadadd7`). All code cites
   are `git show b73f875:<path>` line numbers.
2. `git show b73f875:<path>` read of: `archeus/core/execution/manager.py`, `archeus/harnesses/base.py`,
   `archeus/core/application/executions.py`, `archeus/core/application/work.py`,
   `archeus/core/domain/states.py`, `archeus/core/application/automations.py`,
   `archeus/core/automation/matcher.py`, `archeus/api/auth.py`, `archeus/api/routes.py`,
   `archeus/core/runtime.py`, `archeus/core/engine.py`, `archeus/core/routing/router.py`,
   `archeus/node/local.py`, `archeus/node/isolation.py`, `archeus/cli/tui/_tables.py`.
3. `git grep` at `b73f875` for `DEGRADED|OPEN`, `PairingLocked`, `loop_guard`, `note_failure`,
   `max_attempts`, `dispatch_task`, `EXEC_S`, `health`, and `backoff` restricted to
   `archeus/core/execution/*`, `archeus/harnesses/*`, `archeus/node/*`.
   **Result: no `backoff` anywhere in those three directories** (empty result) — the policy O7
   mandates is absent, matching `reviews/T-102-c91d4f1.claude.md`: "No such mechanism exists yet."
4. Doc greps/reads in `D:/Claude/docs/architecture/`: `p20-design-gate.md` (§4.2 line 371; §12 item
   64 at 1250–1262; item 72 at 1420–1429; open-questions table 2770), `p11-design-gate.md` (§12.4 at
   452–467; O7 at 1018–1022; A1 amendment 1030–1031; note at 951), `pv20-execution-isolation-design.md`
   (309–312, 400, 650, 715, 894), `decisions/ADR-0053.md` (66, 178–179, 220, 430),
   `state-machines.md` §9 (579 ff.), `p14-design-gate.md` (469–470).
5. `D:/Claude/PV20-S1-GATE-2026-10-08.md` §7 read in full: heading line 128, decision line 130,
   verbatim bullets **lines 132–141**, placements §7.3 **157–163**, §7.5 item 10 **181–183**,
   §7.2 "uncharged is a legal value of that delegation" **152–155**.
   Note: the card's `refs:` said "owner decision O7 2026-10-08 … in docs/architecture/"; the decision
   text is not in `docs/architecture/` — it is in the root gate document `PV20-S1-GATE-2026-10-08.md`
   (the two review files also cite it as "PV20-S1-GATE §7"). Recorded in the note, §1.

## Accept criteria — where each is answered (all with file:line)

- **Where O7 is recorded and its exact words** → note §1: the eight verbatim bullets at
  `PV20-S1-GATE-2026-10-08.md:132–141`, plus the deferral/origin chain (`p20-design-gate.md:371`,
  `:1250–1262`, `:1420–1429`, `:2770`; `p11-design-gate.md:1018–1022`, `:1030–1031`;
  `pv20-execution-isolation-design.md:309–312`, `:400`, `:650`, `:715`, `:894`;
  `ADR-0053.md:66`, `:178–179`, `:220`, `:430`).
- **Named vs open (location, threshold, window, reset, visibility)** → note §2: a named/open table
  (charging, dispatch-side location, no-bypass, restart-reconcilability, coarse exhaustion behaviour
  are named) plus nine owner questions Q1–Q9: key/subject, threshold, window, backoff shape,
  reset/recovery trigger, visibility surface, whether the non-isolated permanent-`Popen` loop is O7's
  at all, router-vs-manager blocking point, and whether T-106 may touch the dispatch path with
  `PRODUCTION_DISPATCH_ENABLED` False.
- **Existing breaker code that could carry it** → note §3: execution breaker
  (`states.py:285–303`, `executions.py:825–860`, constants `:799–801`, driven from
  `manager.py:130–132`) — right shape, wrong key, counts only `ENDED_ERROR` + `resource|auth` so it
  cannot see an ABANDONED refusal; harness state (`states.py:395`) — natural key for "a harness that
  cannot spawn", but no failure-driven transitions; pairing breaker (`api/auth.py:198–236`) — right
  shape, in-memory (`:214–215`) so it violates the restart-reconcilability clause if copied; P14 loop
  guard (`automations.py:269–279`, `matcher.py:26–27`, `states.py:263`) — the only existing
  "suspend until the user acts" exhaustion model; plus `BLOCKING`
  (`executions.py:40–42, 211–212, 545–548`) as the already-built halt that answers only the
  post-exhaustion clause.
- **The dispatch path a permanent spawn failure takes today and why it loops** → note §4: three
  cases separated — A: pre-child write → `SpawnWriteFailed` → charged `workspace`
  (`base.py:341–363, 267–271`; `manager.py:324–331`) → bounded by `max_attempts`, no loop; **B: the
  live loop** — `proc.spawn_detached` → `(None, err)` (`base.py:390–396`) → `_refuse` → `SpawnFailed`
  (`base.py:400–408`) → `manager.py:332–341` refuses uncharged `binding` → `UNCHARGED`
  (`executions.py:38–39`) → `_respond` fires `execution_failed_retry` **without consulting
  `max_attempts`** (`executions.py:480–483`; the bound lives only in `charged_failure`, `:490–499`) →
  `binding ∉ BLOCKING` so the mission is not blocked (`:211–212`, `:545–548`) → `EngineLoop`
  re-dispatches (`runtime.py:158–167`, `engine.py:272–280`, `work.py:315–330`) → `tick()` returns
  truthy so `ExecLoop` never idles (`runtime.py:293–295`) → and `accounts_tick` cannot count it
  (`executions.py:838–843`); C: the genuine isolation-establishment failure
  (`base.py:364–376`, `isolation.py:1567–1602`, `local.py:164–172`, `isolation.py:783–799`) — the case
  O7 was written for — is latent behind `PRODUCTION_DISPATCH_ENABLED = False`
  (`isolation.py:86–90`, `requested()` at `:685–696`) and `default_plan` being deliberately
  unsatisfiable (`:1524–1534`).
- **Feeds T-106** → note §5 lists the minimum decision set (Q1, Q2+Q3, Q5, Q6, Q7) and the
  non-negotiables with their sources.

## What was NOT run

- No tests (none of the focused or full `tests/v1` suites), no mutation runs.
- No process started, no `Popen`, no probe, no CLI command against Core.
- No native Windows isolation/profile/ACL operation (no AppContainer create/delete, no `icacls`, no
  `SetNamedSecurityInfo`, no job objects on real processes) — none of these are on this card's `auth:`.
- No web fetch.
- No writes outside `.collab`; nothing staged or committed; no push; no branch switch; no clean/reset.
- The "63 executions in 4 s" and "40 executions in 40 ticks" loop numbers are **quoted** from
  `reviews/T-102-c91d4f1.claude.md` and `p20-design-gate.md:1255–1256/1425–1426`; they were not
  re-measured.
- `py .collab/review.py T-110` was **not** run — this is an analysis card with no commits, which
  `review.py --pending` skips by design; the card's `review:` line routes it to the independent
  Claude reviewer (metadata plus the cited lines).

## Block message

None. No classifier stop, no refusal, no missing authorization encountered. Not blocked.

## Conflict check (affects review routing)

No conflict between canonical documents found — p20 §4.2/§12, p11 §12.4/notes, PV-20 §3.x/§7 and
ADR-0053 all delegate O7 the same way, and the gate §7 decision is consistent with them. Per the
card's `review:` line this stays with the independent Claude reviewer; **no Codex needed.**

*Signed: Qwen.*
