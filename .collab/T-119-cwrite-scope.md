# T-119 · C-write (p21-design-gate D13 (b)): file-scope check

Claude (fork for T-119), 2026-10-19. Read at `b01dc32` (D:/archeus-p21-c). Analysis only: nothing
here is built.

## What C-write has to do

D13 (b) as approved: a command issued from an event or from an approval records that event in its
own events' `cause_chain`; a direct user command stays its own root.

Two facts decide where the change has to go:

1. **The cause is an argument, and it cannot travel any other way.** Every event's `cause_chain`
   comes from the caller: `lifecycle.fire(..., cause=)` → `Tx.transition(..., cause=)`
   (`archeus/infra/db/writer.py:294`), `commands.create_mission(..., cause=)` (`commands.py:86`),
   `automations.py:233/252/263`. A context variable would not reach the event either: commands run
   on the writer's own thread (`writer.py:382` `_run`, fed by `submit()`), so a value set on a
   consumer's thread is not visible where the event is built.
2. **Approval-issued commands run inline in the approval's own transaction.** `authorization.decide`
   fires the plan's `approved` transition and `missions.fire(... 'approve')` / `missions.resume` in
   the same command (`authorization.py:728-744`; `_approve_route` at `:746` likewise). Giving those
   a cause means passing the approval's event id at those call sites.

## Files a C-write diff would touch

| File | Why | Isolation / boundary / credential / auth? |
|---|---|---|
| `archeus/core/application/authorization.py` | approval-issued transitions (`decide`, `_approve_route`, reject paths) must pass `cause=(approval event id,)` | **YES: auth.** Approval decisions, step-up proof checks (`_step_up_valid`), the strike count |
| `archeus/core/missions/intent.py` | consumer handler: commands it issues from `message.created` need `cause=(event.id,)` | no |
| `archeus/core/planning/worker.py` | consumer handler: planning commands issued from mission events | no |
| `archeus/core/knowledge/worker.py` | consumer handler: knowledge commands issued from events | no |
| `archeus/core/automation/worker.py` | already passes `cause` (P14); nothing, or a test only | no |
| `archeus/core/execution/manager.py` | Core's reactions to an execution's end (task/mission transitions) are event-driven | **YES: execution boundary.** It spawns, kills and adopts processes and holds the e-stop path (P20 slices A, E, F, G) |
| `archeus/core/application/missions*.py` / `lifecycle.py` | `missions.fire` / `resume` must accept and forward `cause` | no |
| `archeus/infra/db/writer.py` | **not needed**: `Tx.transition`/`append` already take `cause_chain`. A design that defaulted the cause inside the writer would touch the file holding the idempotency request hash and `PROOF_ARGS` (step-up proofs kept out of the hash, T-107), so that design is rejected here | would be **YES: credential-adjacent** |

## How C-write would avoid writer.py

By passing `cause` explicitly from each issuing site, as `automations.py` already does, never
defaulting it in the writer or the `Tx`. The writer and the idempotency hash stay untouched, and the
cause is not part of any command's hashed arguments, because the issuing sites are Core's own
consumers and inline approval code, not routes with idempotency keys.

## Result of the check

**C-write cannot be shown to avoid the excluded code.** Approval-issued causes require editing
`authorization.py` (auth), and the execution-end reactions run in `manager.py` (the execution
boundary). Under D0 as decided, C-write therefore waits for P20 or for the owner's explicit
authorization naming those two files.

A narrower **C-write-1** is possible without them, if the owner wants it before P20: only the three
consumers (`intent.py`, `planning/worker.py`, `knowledge/worker.py`) and `missions`'
`fire`/`resume` forwarding. It would leave approval-issued and execution-end commands as roots until
the rest lands. That is a scope choice for the owner; it is not recommended here, because a trace
whose causes stop at every approval reads as a gap exactly where the user looks.

C-read (built, `ab6d606`) needs none of this: it reads whatever `cause_chain` holds today.
