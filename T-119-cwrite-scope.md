# T-119 · C-write (p21-design-gate D13 (b)): file-scope check

Claude (fork for T-119). First written 2026-10-19 at `b01dc32` (D:/archeus-p21-c, before the wipe;
recovered from origin `recover/collab-state`). Re-checked and corrected 2026-10-19 after the
restart, at `p21-c` (23e973a on the approved gate d0b98d3); the corrections are marked
**[re-check]**. Analysis only: nothing here is built.

The gate's condition (p21-design-gate.md:175-182): C-write is eligible under D0 only if its diff
touches no isolation, boundary, credential or auth code (nothing in `archeus/node/isolation.py`,
the hook, `authorization.py` or the credential paths).

## What C-write has to do

D13 (b) as approved: a command issued from an event or from an approval records that event in its
own events' `cause_chain`; a direct user command stays its own root. Today the only writer of a
non-empty `cause_chain` is the automation consumer (`automations.py:221-229`: the trigger's chain
plus its id, capped at `MAX_CAUSE_CHAIN` = 16, `events.py:150`).

Two facts decide where the change has to go:

1. **The cause is an argument.** Every event's `cause_chain` comes from the caller:
   `lifecycle.fire(..., cause=)` → `Tx.transition(..., cause=)` (`archeus/infra/db/writer.py:210,
   294`), `commands.create_mission(..., cause=)` (`commands.py:86`), `automations.py`. A context
   variable set on a consumer's thread does not reach the event: commands run on the writer's own
   thread, fed by `Writer.submit()` (`writer.py:326`). It would reach it only if `submit` carried the
   caller's context to the writer thread, which is an edit of `writer.py` (below).
2. **Approval-issued commands run inline in the approval's own transaction.** `authorization.decide`
   fires the approval, then the plan's `approved` transition and `missions.fire(... 'approve')` /
   `missions.resume` in the same command (`authorization.py:625-683, 690-744`; `_approve_route`
   `:747-763` likewise). Giving those a cause means passing the approval event's id at those call
   sites.

Event-issued sources **[re-check]**: the outbox consumers handled through `consumers.deliver`
(`archeus/infra/eventlog/consumers.py:44-62`) are knowledge (`knowledge/worker.py:58`, writes via
`knowledge/passes.py:138`), intent (`missions/intent.py:75`, writes via `intent.py:62`), planning
(`planning/worker.py:78`, writes via `planning/worker.py:65`) and automation (already causal). The
own calls those handlers make write their route decision and call records through
`OwnCalls._do` (`archeus/core/calls.py:63-64`). Not consumers, so roots under (b): the engine and
exec loops (they poll rows, `runtime.py:135-300`), the verification worker ("a scan, not an event
consumer", `verification/worker.py:4`), policy expiry (a timer), the world worker.

Execution end **[re-check]**: the task's response to an execution ending is not a separate
consumer; it runs in the same transaction that appends `execution.ended`
(`archeus/core/application/executions.py:424-433`, `_respond` at `:466`), called by the execution
manager when it observes the process. Under (b)'s wording it is not "issued from an event", so it
may stay a root; if the owner wants `task.state_changed` caused by `execution.ended`, the edit is
in `executions.py`, which also clears `hook_token_hash` on the end paths (`executions.py:351-386, 462, 686`):
hook credential code. The first pass named `manager.py` here; the call site is `executions.py`,
reached from `manager.py`.

## Files a C-write diff would touch

| File | Why | Isolation / boundary / credential / auth? |
|---|---|---|
| `archeus/core/application/authorization.py` | approval-issued transitions (`decide`, `_approve`, `_approve_route`, the reject paths) must pass `cause=(approval event id,)` | **YES: auth.** Approval decisions, step-up proof checks (`_step_up_valid`, `authorization.py:562`) |
| `archeus/core/missions/intent.py` | consumer handler: commands it issues from `message.created` need `cause` | no |
| `archeus/core/planning/worker.py` | consumer handler: planning commands issued from mission events | no |
| `archeus/core/knowledge/worker.py`, `knowledge/passes.py` | consumer handler: knowledge commands issued from events | no |
| `archeus/core/automation/worker.py` | already passes `cause` (P14); nothing, or a test only | no |
| `archeus/core/application/missions*.py` / `lifecycle.py` and the commands the handlers reach | must accept and forward `cause` | no |
| `archeus/core/calls.py` **[re-check]** | only if an own call's records should carry the handler's cause: `OwnCalls.run` would take `cause` | **credential-adjacent**: it resolves the account and passes its `home_ref` to the adapter (`calls.py:118-131`). Leaving own-call records as roots avoids the file |
| `archeus/core/application/executions.py` **[re-check]** | only if execution-end responses are to be caused (see above) | **YES: boundary/credential** (hook token on the same path) |
| `archeus/infra/db/writer.py` | **not needed** with explicit arguments: `Tx.transition`/`append` already take a cause. A design that defaulted the cause in the writer (a `contextvars` cause set by `consumers.deliver`, carried by `submit`, used by `Tx.append`) would edit the file holding the idempotency request hash and `PROOF_ARGS` (step-up proofs kept out of the hash, `writer.py:95-99`, T-107) and the token-row methods `Tx.insert_token` / `revoke_tokens` (`writer.py:132-145`); rejected here | would be **YES: credential-adjacent** |

## How C-write would avoid writer.py

By passing `cause` explicitly from each issuing site, as `automations.py` already does, never
defaulting it in the writer or the `Tx`. The writer and the idempotency hash stay untouched, and the
cause is not part of any route's hashed arguments, because the issuing sites are Core's own
consumers and inline approval code, not routes with idempotency keys. The automation loop guard
does not read chain length (depth comes from automation runs, `automations.py:75-85`), so longer
chains change no automation decision **[re-check]**.

## Result of the check

**C-write cannot be shown to avoid the excluded code.** Approval-issued causes require editing
`authorization.py` (auth). Under D0 as decided, full C-write waits for P20 or for the owner's
explicit authorization naming that file (and `executions.py` if execution-end causes are wanted).

A narrower **C-write-1** touches none of the excluded files: only the three consumers
(`intent.py`, `planning/worker.py`, `knowledge/worker.py` with `passes.py`) and the `cause`
forwarding through `missions`' `fire`/`resume`/`create` and the commands they reach, with own-call
records (`core/calls.py`) and execution ends left as roots. That is a scope choice for the owner;
it is not recommended here, because a trace whose causes stop at every approval reads as a gap
exactly where the user looks.

C-read (built, recovered as `23e973a` on `p21-c`) needs none of this: it reads whatever
`cause_chain` holds today, automation chains only.
