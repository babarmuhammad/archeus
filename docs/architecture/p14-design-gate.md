# P14 design gate: event bus, automation and reactive runtime

Status: **FROZEN (P14), before any P14 code.** Written 2026-09-28 on the P13 baseline (`a99450a`,
CI run 36338455064 green). The as-built record and its deviations are §22. Items are marked as in
the earlier gates:

- **[spec]** already specified by the V1 architecture (plan, domain model, state machines, ADRs);
- **[clar]** a clarification of an existing contract the documents leave open, or that the code
  has already settled differently;
- **[new]** a new contract decision.

Every [new] item and every change to a frozen P1–P13 contract is a numbered decision (§21).

Sources read, in precedence order: the plan (§17, §18, §31.1 **P13, P14**), ADR-0002 (state plus
same-transaction events, one writer), ADR-0020 (automation), domain-model **§3.3, §7.1, §9.4,
§9.5**, state-machines **§2, §8, §14**, api-and-realtime **§1, §3**, execution-architecture
**§8 (AutomationVerifier), e-stop**, testing-strategy **§2 (S10, S10b), §3**, the P4 gate (§4.3:
`repository.model_added` "stays registered for P14's triggers"), the P9–P13 gates; the code:
`core/domain/{events,entities,states,values}.py`, `infra/eventlog/{outbox,consumers,retention}.py`,
`infra/db/{writer,rows}.py`, `core/{engine,runtime}.py`, `core/application/{commands,work,
authorization,queries,world}.py`, `core/{missions,planning,knowledge,verification,world}/worker.py`,
`api/{routes,schemas}.py`, `cli/main.py`, the judge (`client.py`, `http.py`, `support.py`,
`test_s10_automation.py`, `test_s10b_loop_guard.py`). Where a document and the code disagree, the
code says what exists.

---

## 1. Purpose

P14 lets Archeus react, deterministically and safely, to durable facts: *when this happens, ask for
that work*. It answers, from durable state and for every automated piece of work: which event
triggered it, which automation matched and why, what was requested, and everything the normal
mission loop then did with the request.

The rule it enforces: **P14 may cause a request for work. It never authorises, routes, executes,
verifies or continues that work itself.** The only thing an automation can create is a Mission in
state CREATED (ADR-0020), and a CREATED mission reaches a process only through P7 → P8 → P9 → P10
→ P11 → P13, exactly like a mission the user typed.

```
event (committed, seq)
  -> automation consumer (P14)            matches: type, payload predicate, scope, armed
  -> AutomationRun CLAIMED (P14)          unique per (automation, event): the idempotency key
  -> guards (P14)                         stale? depth? rate? disarmed? actor may cause work?
  -> Mission CREATED, origin=automation   the run's ONLY effect outside its own rows
  -> P7 understood -> P5 context -> P8 plan
  -> P9 plan gate (ALLOW | ASK -> approval | DENY)
  -> P10 route  -> P9 dispatch check -> P11 execution
  -> P13 verification -> review -> mission COMPLETED | CANCELLED
  -> run SUCCEEDED | FAILED (P14, from the mission's own event)
```

## 2. Architecture boundary

| P14 owns | P14 consumes, never changes |
|---|---|
| the Automation and AutomationRun rows and machines (state-machines §8) | the mission loop and every guard on it (P7, P8) |
| the `automation` outbox consumer (`archeus-automation`) | policy, approvals, the e-stop (P9) |
| matching, the loop guard, the rate limit, suspension | routing, accounts, models, harnesses (P10) |
| the automation principal of each automation | executions, processes, retries of tasks (P11) |
| emitting `repository.model_added` from a completed inspection (P4 §4.3 left it to P14) | sessions and continuity (P12) |
| a `Hold` signal in `consumers.deliver` (retry without skipping) | verification, review, merge-back (P13) |
| routes and one CLI verb to create, enable, disable, archive, list, simulate and explain | the event envelope and the events table (ADR-0002) |

P14 is **not** a planner, a policy engine, a router, an executor, a verifier, a session system or a
second source of truth. Its module (`archeus/core/automation/`) imports nothing from routing,
execution, sessions, verification, policy, planning, harnesses or the node; a boundary test pins it
(§17 B-*).

Non-goals: schedule and condition triggers (§21 D14), templates shipped by default, an Attention
entity, notifications (P15), any UI (P16), the legacy-loop migration (cutover).

## 3. Event model [spec + clar]

Archeus is **state plus same-transaction events** (ADR-0002) — a deliberately bounded hybrid, not
event-sourced. Every table stays the authority for its own state; an event records that a state
change happened, in the transaction that made it. Nothing is ever rebuilt from events, and P14 adds
no requirement that anything must be.

The envelope (api-and-realtime §3.1, `core/domain/events.py`) already has every field P14 needs; P14
adds **no envelope field** (D1). The prompt's fields map as follows:

| Concept | Field | Why it exists |
|---|---|---|
| event identity | `id` (ULID) | globally unique name of the fact; never reused |
| order / cursor | `seq` | assigned by SQLite inside the writer's transaction: one total order of commits (§6) |
| type | `type` | registered in `TYPES`; an unregistered type cannot be constructed |
| schema version | — (D2) | the registry row is the schema; a payload whose meaning changes gets a new type name. No envelope version: the API version (`/v1`) versions the envelope |
| time | `at` | UTC ms; display and the rate window, never order |
| producer | `actor` (`{kind, id}`, a principal) | who caused it; P14 reads `actor.kind` (§13, D9) |
| aggregate | `subject` (`{kind, id}`) | the row the fact is about |
| causation | `cause_chain` (≤ 16 event ids) | P14 writes it on what it emits: the triggering event's chain plus that event (D5) |
| correlation | — (D3) | the **domain lineage** is the correlation: mission → plan → task → execution → verification → review, joined by foreign keys (P13 §9). An event is correlated by resolving its subject to its mission (§9), never by a second id that could disagree with the rows |
| scope | `workspace`, `project` | P14 does **not** trust the envelope's scope when the subject has a mission: it reads the mission's (D8) |
| visibility | `visibility` | user/system; P14 matches both |
| payload | `payload` | small JSON; predicates read top-level keys only |
| idempotency | — (D4) | P14's idempotency key is `(automation_id, event seq)`, a UNIQUE constraint on `automation_runs`, not an envelope field |

## 4. Durability [clar]

| Survives process, worker, machine restart | Is ephemeral |
|---|---|
| every event (it is a row committed with the state change) | the SSE fan-out's position (a client resumes by cursor) |
| the automation consumer's cursor and effects (`consumer_cursors`, `consumer_effects`) | a retry's attempt count and backoff (§11, D11): a restart grants a fresh budget, which is safe because a failed attempt commits nothing |
| every Automation and AutomationRun row, and the mission a run created | the worker's in-memory status (§16) |
| a quarantined event (an effect row whose result starts `quarantined:`) | |

A temporary database failure raises out of the writer: the consumer's pass fails, the worker thread
fails and Core stops (exit 3), the existing contract for every worker. On restart the cursor has not
moved past the event, so it is delivered again. Nothing P14 claims durable lives only in memory.

## 5. Delivery semantics [spec + clar]

**At-least-once delivery to the handler, exactly-once effect in the database.** `consumers.deliver`
already gives at-least-once (state-machines §14): the handler runs, its effect row commits, then the
cursor moves. P14's handler is ONE writer command per event, and everything it writes — the runs,
the missions, the suspension — commits in that one transaction, guarded by
`UNIQUE (automation_id, triggering_event_seq)`. So:

- a crash before the command commits: nothing was written; the event is delivered again;
- a crash after the command, before the effect row: delivered again; the command finds each run
  already claimed and writes nothing (E03);
- two deliveries at once (two workers, a replay): the writer serialises them; the second finds the
  runs (E20);
- a cursor rewound by an operator (replay): the same (E19).

This is not exactly-once *execution*: a run is claimed exactly once because its only effect is a
row. Whatever the created mission later does outside the database is P11's, with P11's own
guarantees. P14 never claims more (D6).

## 6. Ordering [clar]

One writer assigns `seq` at commit, so `seq` is a **total order of commits** (not of wall-clock
`at`). A consumer receives events in `seq` order, and P14 never skips ahead: an event that fails is
held (§11) and the cursor waits on it; the only way past it is quarantine, which is recorded. Two
events about one aggregate are therefore handled in the order they committed (E21). There is no
ordering across consumers: the automation consumer may be ahead of or behind the knowledge consumer.

## 7. Automations [spec + new]

An Automation (domain-model §9.4, extended by D7):

| Field | Meaning |
|---|---|
| `name` | display |
| `workspace_id`, `project_id?` | its scope: it sees only events of this scope, and creates missions only in it (§13) |
| `trigger` | `{kind: 'event', type, where}` — `type` a registered event type (never `automation.*`/`automation_run.*`, D10); `where` maps a top-level payload key to a scalar (equality), `{glob: p}` or `{not_glob: p}` (fnmatch, case-sensitive). A `state` trigger of ADR-0020 is `type: '<machine>.state_changed', where: {to: STATE}` (D14) |
| `template` | `{title, objective, success_criteria?}` — the mission it asks for. Keys are closed: a template cannot carry a model, harness, account, autonomy profile, plan, approval or verdict (§12, E11, E14). Placeholders `{event.type}`, `{event.seq}`, `{subject.kind}`, `{subject.id}`, `{payload.<key>}`; anything else in braces is refused when the automation is written |
| `max_depth` (3), `rate_limit` (6/hour) | the loop guards (§10) |
| `principal_id` | its own principal, kind `automation`, scope `create_mission` — the actor of every row it writes (§15) |
| `armed_seq` | the outbox head when it was last enabled: it never fires for an event committed before that (D12) |
| `state` | DRAFT → ENABLED ⇄ DISABLED → ARCHIVED; ENABLED → SUSPENDED → ENABLED (state-machines §8) |

Writing and enabling an automation is a **user device** command with the `admin` scope (D13).
PENDING_APPROVAL is not used in P14: enabling authorises nothing, because every action of every
mission is authorised by P9 when that mission plans and dispatches (§8). An automation that "needs
approval to enable" would be approving work nobody has planned yet.

An AutomationRun records one decision: `automation_id`, `triggering_event_seq`,
`triggering_event_id`, `depth`, `cause_chain`, `rationale` (which predicate matched which value),
`reason_code` and `reason`, `mission_id?`, `state`.

## 8. The action-request boundary [spec + new]

The run's machine (state-machines §8), and what decides each edge in P14:

| Edge | P14 condition |
|---|---|
| CLAIMED → SKIPPED `condition_false` | the event is stale (§9), or the automation's project is gone |
| CLAIMED → ESCALATED `depth_exceeded` | the event's causal depth ≥ `max_depth` (§10) |
| CLAIMED → SKIPPED `rate_limited` | `rate_limit` missions already created in the last hour |
| CLAIMED → POLICY_CHECK `conditions_met` | none of the above |
| POLICY_CHECK → SKIPPED `denied` | Core is disarmed (e-stop), or the event was caused by an `execution` principal (§13, D9) |
| POLICY_CHECK → ESCALATED `asks` | not taken in P14: no P9 rule is about *asking for* a mission (D15) |
| POLICY_CHECK → MISSION_CREATED `allowed` | the mission is inserted in CREATED with `origin: automation`, `origin_ref: <run>` |
| MISSION_CREATED → SUCCEEDED / FAILED | the mission's own `mission.state_changed` to COMPLETED / CANCELLED |

"Policy check" here is the admission of a *request*, not authorisation of any action: P9's action
classes are about what work does (`write_repo`, `exec`, `git_push`, …), and P9 judges them at the
plan gate and at dispatch, for this mission as for any other.

## 9. Integration with P7, P8, P9, P10, P11, P13 [clar]

- **P7:** the created mission is `understood from its explicit title and objective`
  (`Missions.understand` already handles an origin with no intent).
- **P8:** the planning worker plans it; P14 supplies no plan and no task.
- **P9:** the plan gate evaluates it under the user's autonomy profile; an ASK stops it at
  APPROVAL_REQUIRED and only a user device can approve (E07, E08). An automation's principal holds
  only `create_mission`, and `authorization.decide` refuses any principal that is not a user device.
- **P10:** the router chooses its resource at dispatch; a template cannot name one (E09, E14).
- **P11:** the execution manager runs it; P14 never touches an execution (E10).
- **P13:** its tasks and criteria are verified by the verification worker; a template cannot carry
  a verdict and P14 writes no verification row (E11). P13's own events (`verification.state_changed`,
  `review.state_changed`) are valid triggers: *verification FAILED → ask for a follow-up mission*
  (E12). The follow-up is a new mission with its own plan, never a retry of the failed task (P11 owns
  task retries).

**Causal lineage.** `mission_of(subject)`: a mission is itself; a plan, task, execution, review,
checkpoint, approval, policy decision, route decision or session names its `mission_id`; a
verification resolves through its plan. **Staleness** (E22): for a `*.state_changed` event whose
subject can be read, the run is SKIPPED `condition_false` unless the subject is still in the state
the event says it entered — the P13 lesson (a verdict judged against a head that moved) applied to
triggers. Other events are facts about the past and are never stale.

## 10. Loop prevention [spec + new]

Three mechanisms, each for a different loop:

1. **Causal depth** (state-machines §8 "escalate, never silently drop"). The depth of an event is the
   depth of the run whose work it belongs to: an `automation_run` subject is that run; any subject
   with a mission is that mission's run when `origin = automation`; anything else is depth 0. A new
   run's depth is the event's + 1; when the event's depth is ≥ `max_depth` the run is ESCALATED and
   no mission is created. Depth follows the **domain lineage, not `cause_chain`** (D5): P7–P13 do not
   propagate cause chains through their commands, and making every command do so would rewrite
   unrelated infrastructure. `automation → mission → task.state_changed → automation` is therefore
   caught however many phases lie between.
2. **Event-type restriction** (D10): an automation cannot trigger on `automation.*` or
   `automation_run.*`, so P14's own bookkeeping can never feed itself.
3. **Rate limit and suspension**: at most `rate_limit` missions per automation per rolling hour;
   three ESCALATED runs, or three `rate_limited` runs, within an hour move the automation to
   SUSPENDED (`loop_guard_tripped`) in the same transaction. A suspended automation fires nothing
   until a user re-enables it, and re-enabling re-arms it (§7): the backlog it missed is not
   replayed. This bounds every loop the lineage cannot see (e.g. through knowledge items).

## 11. Retry, failure and dead letters [new]

Expected outcomes are runs, not failures: stale, escalated, rate-limited, denied and skipped are
all recorded and visible. A **failure** is the reaction command raising (a bug, an unexpected
invariant). Then:

- the worker holds the event (`consumers.Hold`: the batch stops, no effect row, the cursor stays)
  and retries it after a backoff (`RETRY_S`, doubling), so later events wait (ordering, §6);
- after `MAX_ATTEMPTS` (3) the event is **quarantined**: its effect row records
  `quarantined: <error>`, the cursor moves on, and the quarantine is listed by
  `GET /v1/automations` and counted in the worker's status;
- a quarantined event created nothing: the command's transaction rolled back every time. It is never
  retried automatically; an operator who fixes the cause can replay it (rewinding the cursor is
  safe, §5).

A failed dispatch never looks like a successful execution: a run's terminal states are about the
request (SKIPPED/ESCALATED) or about the mission's outcome (SUCCEEDED only when the mission reached
COMPLETED, which requires P13 verification and review).

## 12. Model and harness boundary [clar]

P14 does not select a model, a harness, an account or a model × harness pair, and holds no data to
do it with: a template's keys are closed (§7), the automation module imports nothing from routing or
harnesses (B2), and the created mission has no `resource_preferences`. The eventual chain *task
requirements → model/harness selection → P9 → P10 → P11 → P13* (p13-design-gate §26) is unchanged;
an automation's mission enters it at its start like any other.

## 13. Security [new]

| Threat | Why it fails |
|---|---|
| forged event id, producer, causation, payload | no route or command accepts an event: events are appended only by writer commands, with the command's own actor. There is nothing to forge through |
| an agent manufactures a trigger | an execution may not create missions (domain-model §3.3); an event whose `actor.kind` is `execution` is DENIED as a trigger (D9), so hook reports cannot cause work |
| a user manufactures a privileged trigger | the most a trigger yields is a CREATED mission, which a user device with `control` can create anyway; every privileged action is still P9's |
| wrong aggregate scope, cross-project leakage | the event's scope is resolved from its mission when it has one (D8); an automation matches only events of exactly its workspace and project (both None for a global automation) and creates missions only there (E23) |
| replayed / duplicate events | `UNIQUE (automation_id, triggering_event_seq)` (§5) |
| unauthorised automation creation or enabling | `admin` route scope, and the application command refuses any actor that is not a user device (D13) |
| privilege escalation through automation | the automation's principal holds `create_mission` only; it cannot approve (P9 `decide`), cannot set an autonomy profile or resources, cannot write a verdict |
| actions outside the mission's scope | a mission's actions are bounded by P9 at its gates; P14 adds nothing to a mission beyond title, objective, criteria |
| stale events causing obsolete actions | the stale guard (§9) and `armed_seq` (D12) |
| disabled or archived automation receiving work | the command re-reads the automation in its transaction and matches only ENABLED ones (E05) |
| payload text injected into a mission | substituted values are single-lined, stripped of control characters and cut to 200 characters; the objective remains user-authored text with data slotted in, and the brain treats objectives as untrusted (P7) |

## 14. P12 continuity [clar]

An event is not a transcript. P14 never reads, creates, resumes or hands off a session, and never
reconstructs continuity from events; a mission it creates starts with no session, and any session
work is P12's when that mission's executions run (E13, B2).

## 15. Observability and provenance [new]

`GET /v1/automation-runs/{id}` (and `archeus automation why <run>`) answers the prompt's questions
from rows, with no model reasoning: the triggering event (seq, id, type, actor, subject, scope); the
automation and its trigger; the rationale (each predicate and the value it matched); the depth and
cause chain; the outcome and its reason (suppressed by what, if anything); and, when a mission was
created, the mission's state, its plan versions, P9's policy decisions and approvals, P10's route
decisions (harness, account, model), P11's executions, and P13's verifications and reviews. Every
row it writes names the automation's principal as `created_by`, and `mission.created` carries the
triggering event in its `cause_chain`.

`GET /v1/automations/{id}/simulate?days=30` runs the pure matcher over the retained log (ADR-0020
"simulated before enabling"): which events would have matched, and why — writing nothing.

## 16. Worker health [new — the G01 lesson]

The worker's status is not a transient "idle". `WorldLoop.status()` reports the thread state and
`pending` (events after the cursor), and the automation worker adds `retrying` (events held, with
attempts) and `quarantined` (count). Together they distinguish: no work (`pending 0`), waiting
(`idle`, `pending 0`), working (`running`), retry scheduled (`retrying` non-empty), quarantined, and
failed (thread state). A test that waits on the worker waits for `pending == 0 and not retrying`,
never for one idle observation.

## 17. API and CLI [new]

| Route | Scope | |
|---|---|---|
| `GET /v1/automations` | observe | every automation, the worker's quarantine |
| `GET /v1/automations/{id}` | observe | one automation and its latest runs |
| `GET /v1/automations/{id}/simulate?days=` | observe | the dry run of §15 |
| `GET /v1/automation-runs/{id}` | observe | the explanation of §15 |
| `POST /v1/automations` | admin, idempotent | create (DRAFT) |
| `POST /v1/automations/{id}/state` | admin, idempotent | `{action: enable|disable|archive}` |

`run-now` (api-and-realtime §2) is not built (D14). CLI: `archeus automation list | show <id> |
create <file.json> | enable|disable|archive <id> | simulate <id> | why <run>`.

Boundary tests (B-*): B1 the matcher is pure (no I/O imports); B2 no P14 module imports routing,
execution, sessions, verification, policy, planning, harnesses, node, subprocess or sockets; B3 the
reaction command writes only automation rows, automation-run rows, missions and their events.

## 18. Acceptance scenarios

E01–E25 are the prompt's, in `tests/v1/integration/test_automation.py` unless noted; S10 and S10b
are testing-strategy's judge rows.

| # | Scenario | Proof |
|---|---|---|
| E01 | durable event survives producer restart | event committed, Core closed before the consumer ran, reopened: the run is claimed |
| E02 | duplicate delivery, one side effect | the reaction twice for one event: one run, one mission |
| E03 | crash after the effect, before the ack | reaction committed, effect row never written, redelivered: nothing new |
| E04 | matching is deterministic | unit: same event and automation, same answer and rationale, in any order |
| E05 | disabled automation does not fire | disabled (and archived) before the event: no run |
| E06 | out-of-scope event does not fire | other type, failed predicate, other project: no run |
| E07 | P9 still gates | automation mission under `careful`: stops at APPROVAL_REQUIRED |
| E08 | automation cannot approve | `decide` as the automation principal: NotPermitted |
| E09 | P10 still routes | the automation mission's task carries a RouteDecision |
| E10 | P11 still executes | its execution is the manager's, with an intent row before the spawn |
| E11 | no manufactured verdict | template with verification keys refused; B3 |
| E12 | P13 events trigger follow-up | a verification FAILED event → follow-up mission |
| E13 | continuity stays P12's | B2; the created mission has no session |
| E14 | selection stays outside | template with model/harness/account refused; B2 |
| E15 | causation reconstructible | run → event → mission → plan → execution, from `explain` |
| E16 | loop prevented | self-triggering chain escalates at depth 3 (and S10b) |
| E17 | retryable failure retries | one failure: held, then claimed once |
| E18 | permanent failure quarantined | three failures: quarantined, cursor moves, later events handled |
| E19 | replay is harmless | cursor rewound to 0: nothing new |
| E20 | concurrent duplicates idempotent | two threads react to the same event: one run |
| E21 | ordering | a held event blocks later ones; runs follow seq order |
| E22 | stale event does not override | subject moved on: SKIPPED `condition_false` |
| E23 | no cross-project firing | project A's event never fires project B's automation, even when the envelope says otherwise |
| E24 | restart during dispatch | an automation mission interrupted mid-execution completes once after restart; its run SUCCEEDs once |
| E25 | structured "why" | `explain` names event, automation, rationale, outcome, policy, route, execution, verification |
| S10 | new model file → documentation mission | judge: `repository.model_added` from inspection → mission `origin: automation` |
| S10b | self-trigger escalates at depth 3; three escalations suspend | judge |

Additional (from inspection): X1 an automation never fires for an event before it was armed; X2 an
event caused by an execution principal is denied; X3 suspension re-arms on re-enable; X4 e-stop
denies, and the automation stays ENABLED.

## 19. Mutation strategy (`tools/mutate_p14.py`)

Each mutation removes one invariant, and a named test must fail:

| # | Mutation | Killed by |
|---|---|---|
| A01 | idempotency check removed (second delivery claims again) | E02, E20 |
| A02 | depth ignored (lineage returns 0) | E16 |
| A03 | escalation drops instead of recording | E16 |
| A04 | disabled automations match | E05 |
| A05 | scope from the envelope instead of the mission | E23 |
| A06 | armed_seq ignored | X1 |
| A07 | stale check removed | E22 |
| A08 | execution actor allowed | X2 |
| A09 | e-stop ignored | X4 |
| A10 | a failure advances the cursor (no hold) | E17, E21 |
| A11 | quarantine never reached (retries forever) | E18 |
| A12 | quarantine swallowed silently (no effect record) | E18 |
| A13 | rate limit off | rate test |
| A14 | suspension never trips | S10b unit |
| A15 | template key allowlist removed | E11, E14 |
| A16 | mission created approved-by-default (autonomy set) | E07 |
| A17 | run SUCCEEDs on any mission move | E24/E25 |
| A18 | cause_chain lost on mission.created | E15 |
| A19 | event-type restriction removed | D10 unit |
| A20 | a non-user actor may create an automation | D13 test |

## 20. Implementation order

1. migration 0011, rows, entities, event types; 2. matcher (pure) + units; 3. application commands
and queries; 4. `consumers.Hold`; 5. worker + runtime wiring + judge pump; 6. `repository.model_added`
from the world worker; 7. routes, schemas, CLI, generated docs and client; 8. integration E01–E25,
judge S10/S10b; 9. mutation suite; 10. as-built.

## 21. Decisions

- **D1** No new envelope field. **D2** No per-event schema version; the registry is the schema.
- **D3** Correlation is the domain lineage, not an envelope id.
- **D4** Idempotency is `UNIQUE (automation_id, triggering_event_seq)`.
- **D5** Depth follows mission lineage; P14 writes `cause_chain` on what it emits, and does not
  require P7–P13 to propagate it.
- **D6** At-least-once delivery, exactly-once *claim*; never "exactly-once execution".
- **D7** Automation gains `trigger`, `template`, `principal_id`, `armed_seq`; AutomationRun gains
  `triggering_event_id`, `depth`, `cause_chain`, `rationale`, `reason_code`, `reason`, `mission_id`.
- **D8** Scope is the mission's when the subject has one.
- **D9** An event caused by an `execution` principal cannot trigger work.
- **D10** `automation.*` and `automation_run.*` cannot be triggers.
- **D11** Retry attempts are per process; quarantine is durable.
- **D12** `armed_seq`: enabling never replays history.
- **D13** Only a user device writes or enables an automation; PENDING_APPROVAL unused.
- **D14** Deferred: `schedule` and `condition` triggers, `run-now`, built-in templates. A `state`
  trigger is an event trigger on `*.state_changed`. (Deviation from plan P14 "templates" and the
  testing-strategy "schedule parsing" row; ADR-0020 stands, the trigger's `kind` field is where a
  schedule kind will go.)
- **D15** POLICY_CHECK `asks` is not taken: nothing in P9 asks about requesting a mission.
- **D16** P14 emits `repository.model_added` (one event per new model/schema file between two
  completed inspections; the first inspection of a repository is a baseline and emits none).
  `repository.file_added` stays registered and unemitted.
- **D17** E-stop does not disable automations; while disarmed every run is DENIED and recorded,
  so rearming needs no re-enabling and nothing queued fires late.

## 22. As built

Everything in §1–§21 is built as written, except the deviations below.

**Files.** `archeus/core/automation/{matcher,worker}.py`, `archeus/core/application/automations.py`,
`archeus/infra/db/migrations/0011_automation.sql`; changed: `core/domain/{entities,events}.py`,
`infra/db/rows.py`, `infra/eventlog/consumers.py` (`Hold`), `core/application/commands.py`
(`create_mission` takes `origin`, `origin_ref`, `cause` from Core's own callers — no route passes
them), `core/world/{inspection,worker}.py` + `core/application/world.py` (`repository.model_added`),
`core/runtime.py` (`archeus-automation` thread, `/v1/health` key `automation` with `retrying` and
`quarantined`), `api/{routes,schemas}.py`, `cli/main.py` + `claude_sessions/cli.py` (verb
`automation`), `pyproject.toml` (`archeus.core.automation`), the generated API reference and
TypeScript client, `tools/{gen_api_docs,mutate_p14}.py`.

**Tests.** `tests/v1/integration/test_automation.py` (E01–E03, E05–E07/E08, E09/E10/E15/E25,
E11/E14, E12, E13, E16 + X3, rate limit, E17–E24, X1, X2, X4, D13, simulation — 25 tests),
`tests/v1/integration/test_automation_http.py` (the six routes: scopes, idempotency, 400/403/404,
the runtime worker on its own thread), `tests/v1/unit/test_automation_units.py` (E04, predicates,
trigger and template refusals, rendering, the suspension rule, B1, B2), judge S10 and S10b (no
longer xfail).

**Deviations.**

1. **The judge's S10/S10b were rewritten** [clar]. The P1 drafts named fixture repositories that
   were never built (`django-app`, `self-triggering-automation`) and read `status()['attention']` and
   `status()['automations']`, which no phase added (there is no Attention entity; P16 builds that
   surface). They now go through four new contract operations (`create_automation`,
   `set_automation_state`, `automations`, `automation`; testing-strategy §1.1 updated first): S10
   commits `billing/models/invoice.py` into `layered-python` and waits for the documentation mission;
   S10b self-triggers on `mission.created` and asserts the depth-4 escalation and the suspension.
2. **E09 runs on P10's real router.** The skeleton's stub router records no RouteDecision, so the
   route half of E09/E25 needs `ResourceRouter` over the fake harness (`Rig(real_router=True)`).
   `explain` resolves a mission's routes by the `mission_id` column and through each execution's
   `route_decision_id`.
3. **One settle predicate.** Mutation A17 first survived: the worker's cheap relevance filter
   repeated `_settle`'s condition, so breaking either copy alone changed nothing. Both now call
   `automations.settles(e)` (the Z09 lesson: a mutation must hit the layer that actually holds).
4. **Mutation list.** A16 as drafted ("mission created approved by default") has no plausible site:
   `create_mission` accepts no autonomy profile or resources, so there is nothing to mutate. A16 is
   "a non-admin writes an automation", A20 "a non-admin enables one", and A21 was added: "a held
   event is overtaken" (`consumers.Hold` → `continue`).
5. **An event nothing matches costs no write.** The worker reads first (`_relevant`) and runs the
   `react` command only for a settle or a candidate; `react` re-derives everything in its own
   transaction, so the read decides only whether to ask.
6. **E13** is proven by rows (the created mission has no session) plus B2 (no P14 module imports
   sessions), not by a session-triggered automation.
7. **A retry runs at the worker's next pass after its backoff** — the next commit, or the thread's
   poll interval — not on a timer of its own; the backoff is a floor, not a schedule.
8. `MODEL_GLOBS` (D16): `models/*`, `*/models/*`, `*models.py`, `*.prisma`, `schema.*`,
   `*/schema.*`.

**Known limitations** (none is a safety gap; each is bounded by §10 or stated in the gate):
causal depth follows mission lineage only, so a loop through knowledge items is stopped by the rate
limit and suspension, not by depth; retry attempts are per process (D11); the simulation evaluates
trigger and scope, not depth, rate or state; an ESCALATED run is terminal — the user acts on it by
creating the mission themselves (no "proceed anyway"); no notification is sent (P15); `schedule`
and `condition` triggers, `run-now` and built-in templates are deferred (D14);
`repository.file_added` stays unemitted (D16).
