# P7 design gate: brain, intent and mission engine

Status: **IMPLEMENTED (P7).** Written 2026-09-26 against `349c3d4` (P6 closed). The decision
pass accepted D1–D8 as recommended (§14); D9–D22 follow from the documents' own precedence rules
and are recorded here rather than asked.

Sources read, and precedence: the plan (§11, §31.1 **P7**, P8, §31.4), **ADR-0006**, ADR-0015,
**ADR-0021** (still OPEN), **ADR-0022**, ADR-0023, context-and-knowledge **§2–§3, §8**,
domain-model **§4, §6, §7.1, §7.8**, state-machines **§1, §2, §11**, api-and-realtime §2–§3,
testing-strategy §1.1, **§2 (S1, S9, S13, S15, SP3)**, the P5 and P6 gates, and the code:
`archeus/core/{engine,runtime,calls,ports}.py`, `application/*`, `context/*`, `knowledge/*`,
`archeus/harnesses/fake.py`, `archeus/api/*`, the judge. Where a document and the code disagree
the code states what exists; where two documents disagree the more specific one wins, and the
frozen judge is the most specific.

---

## 1. What P7 is

P6 **derives** knowledge; P7 **understands the user**: what a message asks for, whether it is
work, which existing objects it concerns, whether it must be clarified or challenged, and — only
when all of that holds — the Mission (or Idea, or feedback) it becomes. It never plans (P8),
authorises (P9), routes work (P10), executes (P11), continues sessions (P12) or verifies (P13).

```
user message.created                                     (POST, or the in-process binding)
  -> intent worker (outbox consumer, archeus-intent)
     -> a reply to "when was that meeting held?"  -> the meeting is dated        no model
     -> the control grammar resolves it           -> the verb is applied         no model
     -> otherwise:
        ContextPackage for the MESSAGE           (P5's engine, subject `message`)
        archeus_call(purpose brain, intent.v1)   (P6's path: election, RouteDecision first,
                                                  ADR-0021 re-check, native or prompted,
                                                  Core validation, one retry)
        handles resolved to {kind, id}           (an unknown handle is invalid output)
        ONE command: decide deterministically, write, end the call
          question            -> answer; every claim cites an object
          ambiguity / unknown -> clarification (nothing else written)
          conflict            -> challenge (the user chooses; no mission)
          new_work            -> Mission CREATED   (or an Idea promoted)
          continue_work       -> the open mission's requirements grow
          idea                -> Idea CAPTURED
          feedback/preference -> P6's record_feedback: history + at most a CANDIDATE
```

The invariant: **the model reads; Core decides.** Raw model output never reaches a row: it is
schema-checked, handle-checked, kind-checked, resolved, and then re-judged against the rows of
the transaction that applies it.

## 2. Boundaries

| | |
|---|---|
| **P7 owns** | `core/application/{grammar,conversation}.py`, `core/brain/intent.py` (`intent.v1`), `core/missions/intent.py` (the worker), `Missions.understand`, the `message` context subject, migration 0006, three event types, five routes, `FakeCaller` recordings (`when`) |
| **P7 consumes** | P5's `record_context_package`, P6's `archeus_call` and ProviderTerms gate, P6's `record_feedback`/`confirm`/`new_item`, P3's `Missions` actions and the Idea machine, P4's deterministic `status()` |
| **defers** | mission threads (one Conversation per mission, ADR-0015) and the SPA surfaces to P16; confirmation before a mission starts (the autonomy profile) to P9; approve/reject/reprioritise to P9/P10; a mission-level challenge in REASONING (§6) to P8; Person/Organization resolution until those entities have rows |
| **never** | a plan, task, execution, session or non-brain RouteDecision from an intent; a CONFIRMED item from a model's reading; a world entity created from a name the model produced |

## 3. The brain call (ADR-0006, ADR-0022, ADR-0021)

**No new call abstraction.** The intent read is one `OwnCalls.run(purpose='brain', …)` — P6's
`archeus_call`, unchanged: the pre-router election over installed `headless` adapters (the
user's choice, else Claude Code, else the first), the RouteDecision committed before the call,
the provider-terms re-check immediately before the spawn (fakes exempt by class identity only),
the harness's own account and model vocabulary, `adapter.call()` with native or prompted
structured output, and Core validation with one retry. So P7 needs no Claude: any harness
declaring `headless` reads intent (I11), and a real adapter without the user's ADR-0021 answer is
never called (I12). ADR-0021 stays **OPEN**; with the real adapters P7 makes no real call.

**`intent.v1`** (`core/brain/intent.py`): `kind` (question / new_work / continue_work / feedback /
preference / idea), `title`, `objective`, `desired_outcome`, `target`, `project`, `mentions`,
`requirements` and `constraints` (each `origin: explicit | inferred`), `ambiguities` (each
`material`), `conflicts`, `feedback` (`signal`, `title`, `promote`, `supersedes`), `answer`
(claims, each citing handles) and `confidence`. The model names objects **only by handles** the
prompt gives the package's items (`p1` project, `m1` mission, `i1` idea, `k1` knowledge, `u1`
earlier turn, `g1` meeting); ids never cross the model boundary in either direction. Core's check
(`brain.check`) refuses an unknown handle, a handle of the wrong kind for where it is used (a
continuation must name an open mission, a promotion an idea, a conflict a deciding item), a
question whose claim cites nothing, a preference that does not state itself. A refused answer is
retried once; a second refusal ends the call `invalid`, and the reply says the message could not
be read — ADR-0006's "then ask" (P6 §12.5) is that reply.

**D7 (accepted): asynchronous.** `POST /v1/conversations/{id}/messages` records the turn and
returns its id; the `archeus-intent` worker reads it and writes the reply (`message.created`), as
api-and-realtime §2 states. The judge's `submit_message` waits for the reply and for Core to
settle what it set in motion.

## 4. Persistence (migration 0006)

`conversations` (kind, mission_id), `messages` (conversation, author, `in_reply_to`, all
indexed; cards and links in the body), `intents` (**`message_id UNIQUE`**: one message is read
once, so no retry or redelivery can make a second intent — or mission), `ideas` (state as a
column). Mission gains `origin_ref`, `desired_outcome`, `requirements`, `constraints`
(domain-model §7.1, in the body: no migration); Meeting's `held_at` becomes optional (D2);
Intent gains `via`, `workspace_id`, `project_id`, `target_refs`, `ambiguities`, `conflicts`,
`confidence`, `resolution`, `reason`, `proposal`, `route_decision_id`, `context_package_id`,
`answers_intent_id`; Message gains `in_reply_to`, `cards`, `links`, `intent_id`, `principal_id`;
Idea gains `title`, `origin_message_id`, `promoted_mission_id`. Card types add `mission`, `idea`,
`challenge`, `clarification`, `knowledge`, `status` to the documented set (S15 and SP3 name two).

**D6 (accepted): three event types, no more.** `idea.created`, `idea.state_changed` (the writer
already requires `<machine>.state_changed` for any Idea move, state-machines §0) and
`mission.updated` (a continuation added requirements or constraints). An intent, a
clarification and a challenge are rows plus the reply's existing `message.created`, whose
`cards` say which. `intent.created`, `intent.updated` and `clarification.requested` are not
registered.

## 5. Intent interpretation, as built

| kind | decided by Core as | writes | resolution |
|---|---|---|---|
| control verb (grammar) | pause / resume / stop·cancel a mission through `Missions`; `status` (P4's deterministic status); `why <id>` (the RouteDecision's own explanation); `remember [that] …`; approve / reject / reprioritise recognised and declined until P9/P10 | the verb's own rows, an Intent `via: grammar`, the reply | answered / mission_updated / declined |
| question | an answer whose every claim cites an object in the package | Intent, reply with `links` | answered |
| new_work | a Mission in CREATED (`origin: conversation`, `origin_ref`: the message), requirements and constraints kept explicit vs inferred; with an idea as `target`, the idea is promoted instead | Mission, `mission.created` | mission_created |
| continue_work | the named open mission's requirements/constraints grow; nothing new → noted, not claimed as an update | `mission.updated` | mission_updated / answered |
| idea | an Idea in CAPTURED — not a commitment | Idea, `idea.created` | answered |
| feedback | P6's `record_feedback` about its target (mission, knowledge item, message), promoting only when asked | Feedback (+ CANDIDATE) | answered |
| preference | P6's `record_feedback` about the message, promoting a PREFERENCE **CANDIDATE**, naming the item it replaces | Feedback, CANDIDATE, `supersedes` relation | answered |
| (the call failed) | gated, unavailable, invalid, failed: the reply says why; the unread message's Intent is recorded as `question` (the kind that writes nothing) with the outcome in `reason` | Intent, reply | declined |

A grammar verb matches only whole, and only when its reference resolves to exactly one object (an
id, or one open mission's / one project's exact title): "stop everything please" is not a
command, it is read. **D21:** the grammar's `remember …` is the one path to a knowledge item that
confirms itself (origin explicit, §3's "remember that … → auto-confirm"); a model's reading of a
preference is always a CANDIDATE (S9). That resolves the tension P6 §12.1 left for P7.

## 6. The Mission boundary

A Mission is created **only** by a `new_work` reading that is unambiguous, names nothing that
cannot be found, and goes against nothing it could be challenged on — or by the user's `proceed`
on a challenge (D16). Everything else makes no mission. The mission starts in CREATED and moves
only through P3's actions: the engine's `start`, then **`Missions.understand`** (UNDERSTANDING →
CONTEXT_GATHERING), which replaces the walking skeleton's stub and records where the
understanding came from — the message and its intent, the promoted idea, or the explicit title
and objective of a mission created through `POST /v1/missions`. Because a mission exists only
once understood, `needs_clarification` is not taken in P7 (D12). REASONING's `challenge_raised`
edge is not taken either: the challenge happens at intent time, before any mission exists
(plan §11 step 3, "instead of a mission"); a second, mission-level challenge against project
knowledge the message's package could not rank would be a brain call in REASONING, which is the
planner's state (P8). Whether a mission waits for the user's confirmation before it starts is the
autonomy profile's (P9); the P1 policy stub never asks (D13).

**Existing missions (D14):** a `continue_work` reading must name an open mission by handle; Core
re-checks it is still open in the applying transaction (a mission that ended meanwhile turns the
reading into a clarification, I20). No reading ever creates a mission to continue.

**Idempotency (D15):** a retried POST carries the same idempotency key and returns the same
message (the writer's key store); a re-delivered event finds the message's intent and stops; the
UNIQUE index stops a race between the two. I15 proves all three.

## 7. Clarification and challenge

**Clarification** is asked when a work reading (new_work, continue_work, idea, feedback,
preference) carries a **material** ambiguity, names a project / mission / idea the package does
not contain (**D10: never invent a canonical object** — a person, organisation or system named
is recorded, but those have no rows to resolve against in V1), or targets something that changed
since it was read. Confidence is recorded and never decides (D11, P6's D4 rule). The reply
carries a `clarification` card on the Intent; the user answers by replying to it (`in_reply_to`),
or through `POST /v1/intents/{id}/clarify {text}`, which posts that reply. The answer is read
like any message, with the question in view, and its Intent names `answers_intent_id`.

**Challenge (D1, accepted):** a `new_work` or `continue_work` reading whose `conflicts` name
CONFIRMED DECISION / ARCHITECTURE / STANDARD / PREFERENCE items, **or DECISION candidates
imported from meeting notes**, is challenged instead of applied. A candidate is labelled `not
confirmed` everywhere — in the package (the `candidate` authority, 0.3), in the prompt, and in
the challenge's text — and nothing about it changes: note-derived decisions stay CANDIDATE (P6,
N22), and P7 never presents one as confirmed. The user chooses through
`POST /v1/intents/{id}/clarify {choice}`: `proceed` applies the recorded reading as validated
(no second model call), with the conflict noted as an explicit constraint; `drop` declines it.
A choice is taken once.

## 8. Feedback and corrections

Feedback is history (domain-model §7.8), recorded by P6's `record_feedback`; promotion is only
ever to a CANDIDATE. "No, I meant X" is read against the conversation's earlier turns (the
package's L0), so it becomes a `continue_work` of the mission just created, a `preference` that
replaces the preference just stated, or a new `question` — never new work by default. This is
the conversation's own history, not session continuity (P12).

**Candidate → candidate lineage (D4, accepted).** A promoted candidate may name the live item it
replaces, CANDIDATE or CONFIRMED (`supersedes_id`, plus an EXTRACTED `supersedes` relation from
the feedback). Nothing changes state at promotion. When the newer candidate is **confirmed**:
a CONFIRMED predecessor becomes SUPERSEDED (P6, unchanged); a CANDIDATE predecessor is
**rejected** (CANDIDATE → RETRACTED, the only edge its machine has) with the reason `replaced
before it was confirmed`, `valid_until` and `superseded_by_id` — it is never SUPERSEDED and was
never authoritative. The chain (`get_knowledge.chain`) stays whole. N21 passes unchanged.

## 9. Context (D5, accepted) and knowledge

P5's engine gains one subject kind, **`message`**, and P7 builds nothing of its own: L0 the
message and its conversation's earlier turns (with what each produced), L1 the workspace's
projects (what names resolve against), L2 open missions, live ideas, meetings and every project's
CONFIRMED deciding items and preferences, L4 global knowledge. Relevance and the per-level budget
decide what is shown, as for any subject. The mission and project subjects are untouched:
candidates stay excluded there. For a message only, a DECISION candidate imported from notes is
shown at the `candidate` authority, labelled not confirmed (D1). The package is recorded with
`context_package.created`, and the RouteDecision and the Intent cite it.

A message is read against what was learned **before** it: the runtime's intent worker waits (at
most 300 s) until the knowledge worker has consumed every earlier event, so notes imported and
then asked about are known when the question is read (D17). The in-process binding pumps the
knowledge worker first, which gives the same order.

P7 writes knowledge only through P6's commands: a CANDIDATE from feedback, and the grammar's
explicit `remember`. Nothing a model says becomes CONFIRMED.

## 10. Meetings (D2, accepted)

Undated notes are imported **only when the import path opts in** (`allow_undated`), with
`held_at` empty — never the clock's or the file's date — and the same command asks for the date
in the primary conversation (a `clarification` card with `asks: held_at`). `read_notes` alone
still refuses (N23), and the route still answers 400 without the opt-in (N31). The user's reply
to that question sets `held_at` (recorded by the reply's `message.created`, D18).

## 11. Routes

| Route | Scope | Idempotency |
|---|---|---|
| `GET /v1/conversations/{id}/messages?after` (`primary` names the primary one) | observe | — |
| `POST /v1/conversations/{id}/messages` `{text, in_reply_to?}` | control | required |
| `GET /v1/intents/{id}` | observe | — |
| `POST /v1/intents/{id}/clarify` `{choice: proceed\|drop}` or `{text}` | control | required |
| `GET /v1/ideas?state` | observe | — |

`/v1/health` gains `intent: {state, pending}`, which the HTTP judge's idle signal reads.
`POST /v1/meetings/import` gains `allow_undated`. `CoreClient.submit_message` is implemented in
both bindings; `import_meeting` opts in to undated notes in both.

## 12. Acceptance and tests

| # | Test | Phase |
|---|---|---|
| S1 | `test_s01_simple_mission.py` — a request becomes a mission with a proposed plan (passes); completes after verification and review (**passes on the P3.5 stubs, marker removed, D3**); **new** `test_the_review_is_independent_of_the_work_it_reviews` (strict `phase:P13`) | P7–P13 |
| S9 | `test_s09_feedback_to_knowledge.py` — a CANDIDATE preference; a superseding one names its predecessor | P7, **passes** |
| S13 | `test_s13_status.py` — the brain summary links every claim | P4, P7, **passes** |
| S15 | `test_s15_idea_to_mission.py` — idea captured, then promoted (`origin: idea`) | P7, **passes** |
| SP3 | `test_sp03_challenge.py` — undated notes imported, their DECISION candidate challenged, no mission | P7, **passes** |
| U01, U03–U08 | `tests/v1/unit/test_intent_units.py` — the grammar table, the schema, Core's checks per kind and handle, resolution, handles, import boundaries (AST and a fresh interpreter) | P7 |
| I01–I22 | `tests/v1/integration/test_intent.py` — question vs work, one mission with provenance, continuation, ambiguity, project resolution and no invented project, challenge proceed/drop, only deciding items, ideas and their machine, feedback and candidate lineage, `remember`, the P5 package, native and prompted, another harness, the gate, invalid and malformed output, idempotency and redelivery, the lifecycle, no execution/plan/route, control verbs without a model, undated notes, a stale reading, grammar resolution (U02), a continuation updates exactly the mission it names | P7 |
| H01–H04 | `tests/v1/integration/test_intent_http.py` — the routes, retry, opt-in undated import, the challenge choice, a clarification answered by text | P7 |

**Mutation suite: 18/18 killed** — an idea made a mission, clarification bypassed, the wrong
mission continued, Core's checks bypassed, no schema on the call, an unknown project guessed, the
idea's identity replaced, the idea machine bypassed, a retried message read twice (all three
guards off), a challenge chosen twice, a plan created early, the provider-terms gate bypassed, a
conflict not challenged, a note candidate shown as confirmed, a model preference confirmed, a
candidate predecessor SUPERSEDED, a control verb sent to the model, an undated meeting dated by
the clock.

The judge's default Core is offered one scripted harness (**D8**): a FakeCaller replaying
`tests/v1/fixtures/brain/recordings.json`, whose entries answer any prompt containing their
`when` text. A pass no recording answers ends `failed` instead of P6's `gated`; no scenario
asserts either.

## 13. Deviations from the architecture documents

1. **The plan §11 challenge rule widens (D1):** conflicts with CONFIRMED knowledge *or with a
   DECISION candidate imported from notes*, labelled not confirmed. SP3's docstring says
   "CONFIRMED"; its body, and P6's N22, are unchanged.
2. **Undated notes are imported on opt-in (D2):** P6's D16 refusal stays the default.
3. **S1's second function lost its P13 marker (D3):** it passes on the P3.5 stubs; a new strict
   P13 function keeps the row pending.
4. **A candidate may name a candidate predecessor (D4):** P6's CONFIRMED-only rule for
   `record_feedback` widens; confirmation semantics do not.
5. **The context engine has a third subject, `message` (D5)** (domain-model §5.3 lists two).
6. **Three event types are added (D6)** to api-and-realtime §3.2's registry.
7. **Card types extend domain-model §6's list** (S15, SP3 name `idea`, `challenge`).
8. **No mission threads:** every turn is in the primary conversation, and a message links the
   mission it touched (ADR-0015's per-mission Conversation is P16's surface).
9. **The challenge is at intent time only;** REASONING's `challenge_raised` and UNDERSTANDING's
   `needs_clarification` are not taken in P7 (§6).
10. **Schemas live in `core/brain/intent.py`,** not a `core/brain/schemas/` directory (ADR-0006):
    one schema, beside the checks that read it, as P6's passes keep theirs.
11. **A meeting's date is recorded by the reply's `message.created`**, not an event of its own
    (D6 allowed no `meeting.updated`).
12. **Plan §31.1 names `brain/calls.py` "on the P0.5 llmcall runner; account from rotate/quota"**:
    that is exactly P6's `archeus_call` and harness adapters, reused rather than rebuilt (D9).

## 14. Decision pass

| # | Decision | Outcome |
|---|---|---|
| D1 | Challenge on CONFIRMED deciding items and on meeting DECISION candidates, labelled not confirmed | **accepted** |
| D2 | Undated notes: imported on opt-in with no date, then asked | **accepted** |
| D3 | S1's stub-satisfied P13 function unmarked; a new strict P13 function | **accepted** |
| D4 | Candidate → candidate lineage; confirmation rejects a CANDIDATE predecessor, supersedes a CONFIRMED one | **accepted** |
| D5 | P5 subject `message` | **accepted** |
| D6 | Events: `idea.created`, `idea.state_changed`, `mission.updated` only | **accepted** |
| D7 | Asynchronous intent worker; `submit_message` waits for the reply | **accepted** |
| D8 | The judge's recorded FakeCaller (`when`) | **accepted** |
| D9 | The brain call is P6's `archeus_call`, purpose `brain` | ADR-0022, "no new abstraction" |
| D10 | An unfound project / mission / idea is a clarification, never a new row | domain-model §4, no hallucinated world |
| D11 | Confidence recorded, never decides | P6 D4 |
| D12 | `understood` from the intent; `needs_clarification` not taken | a mission exists only once understood |
| D13 | No confirmation before a mission starts in P7 | autonomy is P9 |
| D14 | A continuation must name an open mission, re-checked when applied | no duplicate missions |
| D15 | One intent per message (UNIQUE), idempotent POST, redelivery skipped | api-and-realtime §2 |
| D16 | A challenge's `proceed` applies the recorded reading without a second call | ADR-0006: Core applies |
| D17 | A message is read after the knowledge learned before it (bounded wait) | S8/SP3 order |
| D18 | A meeting's date is set by the reply to its question | D6 allowed no new event |
| D19 | Idea promotion takes only the diagram's shortcuts (`clarify`, `plan`, `promote`) | state-machines §1 |
| D20 | An idea follows its mission (`mission_completed` / `mission_cancelled`), consumed from the outbox | state-machines §1 |
| D21 | `remember …` (grammar) confirms itself; a model's preference is a CANDIDATE | context-and-knowledge §3, S9 |
| D22 | approve / reject / reprioritise recognised, declined until P9/P10 | ADR-0006 grammar, phase order |

**DESIGN_GATE = IMPLEMENTED.**
