# P6 design gate: knowledge and learning

Status: **IMPLEMENTED (P6).** Written 2026-09-26 against `018bb6b` (P5 closed). The decision
pass accepted D1–D7 as recommended (§14); D8–D18 follow from the documents' own precedence rules
and are recorded here rather than asked.

Sources read, and precedence: the plan (§11, §31.1 **P6**, P7, §31.4, §32), **ADR-0021**,
**ADR-0022**, ADR-0023, ADR-0006, ADR-0012, ADR-0013, context-and-knowledge **§2–§5, §8**,
domain-model **§4, §5, §7.8, §8**, state-machines §11, execution-architecture **§3**,
resource-router **§3, §8, §9**, api-and-realtime §2, migration-plan §2.4 and §3,
testing-strategy §1.1, **§2 (S8, S9)**, **§6 (K1–K3)**, the P5 gate, and the code:
`archeus/core/{engine,runtime,ports}.py`, `application/*`, `context/*`, `world/*`,
`archeus/harnesses/*`, `archeus/api/*`, `archeus/infra/{db,eventlog,artifacts}`, the judge, and
the legacy modules P6 reuses (`claude_sessions/{llmcall,memory,pi,harnesses,config,rotate,
quota}.py`). Where a document and the code disagree the code states what exists; where two
documents disagree the more specific one wins, and the frozen judge is the most specific.

---

## 1. What P6 is

P5 **selects** existing information; P6 **derives, validates, stores and maintains** durable
knowledge. P6 is the first phase with a real model call, so it is where ADR-0022's call path and
ADR-0021's gate become code:

```
pass (knowledge | decisions | lessons)
  -> ContextPackage recorded for what the call is about          (P5's engine)
  -> archeus_call: pre-router election -> RouteDecision committed
  -> provider-terms re-check, immediately before the spawn        (ADR-0021)
  -> the harness's own account and model vocabulary               (ADR-0022)
  -> adapter.call(): native or prompted structured output
  -> Core validation (schema, then the pass's own checks; retry once)
  -> CANDIDATE knowledge + relations + the call's end, one transaction
```

The invariant: **model output is never confirmed truth.** It enters as CANDIDATE with its
provenance; only the user, an explicit origin, or — for a lesson — corroboration by two distinct
missions confirms it. Nothing is deleted.

## 2. Boundaries

| | |
|---|---|
| **P6 owns** | `archeus/core/calls.py` (`archeus_call`), `core/application/{calls,knowledge}.py`, `core/knowledge/{passes,worker,ingest}.py`, `harnesses/calls.py` (the real `call()` of claude_code and pi), `FakeCaller`, `CallSpec`/`CallResult`, `Capabilities.structured_output`, migration 0005, the ProviderTerms gate, 13 routes, `archeus terms` |
| **P6 consumes** | P4's inspections (the knowledge pass's input), P5's `record_context_package` (every pass records the package it is given), the engine's mission ends (lessons), the P0.5 `llmcall` runner |
| **defers to P7** | intent (S9: which message is feedback, which preference it supersedes), the brain, the Decision entity's mirror, asking the user after invalid output, Person links for meeting attendees, relation expansion into context |
| **defers to P10** | the router (K1's last function), Account/ModelOffer rows and model-offer validation, provider profiles for own calls (legacy `headless_provider_id`) |
| **defers to P14** | consolidation, backup → verify → swap, lesson decay by usage (needs hits, which a read-only context engine cannot write) |
| **never** | a real call before the user's ADR-0021 answer; a call that is an Execution or a Session; a knowledge write outside a writer command; a prose/similarity contradiction |

## 3. Model calls and the provider-terms gate (ADR-0021)

**D2 (accepted).** One `ProviderTerms` row per harness id: `headless` and `rotation`, each
`unknown | permitted | refused`. **No row is `unknown`, and `unknown` blocks exactly as `refused`
does.** Only the user gives an answer — `POST /v1/provider-terms/{harness}` (admin) or
`archeus terms <harness> permit|refuse [--rotation …]` — and the command refuses any other
principal kind. `provider_terms.decided` records it. The gate runs twice: as an eligibility step
of the election (a real adapter without `permitted` is eliminated with reason `provider terms …`),
and again **immediately before the spawn** in a fresh read, so an answer withdrawn between the two
still stops the call. Scripted adapters are exempt by **class identity** (`type(a) is FakeCaller`),
the registry gate's rule: a subclass or an impostor id is gated. Rotation across subscriptions
(Claude Code's `rotate.elect()`) runs only when `rotation` is `permitted`; otherwise the active
account is used. ADR-0021 itself stays **OPEN**: the mechanism is built, the answer is the user's,
and until they give it P6 makes no real call.

## 4. Persistence (migration 0005)

`relations` (flat `src_kind, src_id, rel, dst_kind, dst_id`, both ends indexed), `meetings`,
`feedback`, `route_decisions`, `usage_ledger`, `provider_terms`. KnowledgeItem gains its
provenance fields (§6). **D9:** no `decisions` table in P6 — a decision read from notes is a
DECISION knowledge *candidate*; the Decision entity (the mirror of a *made* decision) arrives with
the phase that records decisions made in conversation (P7).

## 5. `archeus_call` (ADR-0022)

- **Election (pure, `calls.elect`)**, over the adapters sorted by id: eliminated when not
  installed, not `headless`, or (real adapters) not permitted by the terms; then your choice if
  it survived, else `claude_code`, else the first by id. Every candidate is recorded with the step
  it was eliminated at (`installed`, `headless`, `provider_terms`, `election`).
- **Model:** `OwnCallPreference.model_for(harness)` — Claude Code's own calls use the legacy
  `extract_model`; any other harness gets `headless_harness_model` only when it is the harness it
  was chosen for. A model set for one harness is dropped for another, never translated.
- **The RouteDecision is committed before anything runs** (`decided_by: pre_router`,
  `subject: archeus_call/<purpose>`, `source`, `requirements`, `candidates`, `input_snapshot`
  with the preference and the terms, the generated `explanation`, the `context_package_id`). Its
  `outcome` is written once, when the call ends (`ok | gated | unavailable | model_unavailable |
  timeout | failed | invalid`), with a UsageLedger row carrying the RouteDecision — **a call has
  no Execution and no Session**. `route.decided` and `archeus_call.ended` record both halves.
- **Validation:** the answer must parse, match the pass's schema (a JSON-Schema subset now in
  `core/domain/shapes.py`, shared with the API) and pass the pass's own checks (non-blank names,
  no duplicate entity, 2 KB bodies). Invalid output is retried **once** (ADR-0006); a second
  invalid answer ends the call `invalid` and writes no knowledge. ADR-0006's "then ask" is P7's.
- **Adapters (D3, accepted):** `ClaudeCodeCaller` — `llmcall.build_headless_args` (write tools
  disallowed, `--max-turns`, budget, HEADLESS_MARK) plus `--output-format json --json-schema`
  (native); account from `rotate.elect()`/`quota.reason()`. `PiCaller` — `pi -p --no-session
  --tools read,grep,find,ls [--model provider/id]`, the schema in the prompt (prompted), pi's home
  env. Both run on `llmcall.run_headless`, never enter the P1 AdapterRegistry, and have no
  `start()`. Codex declares no `headless` (as on main).

## 6. The knowledge model, as built

| | |
|---|---|
| **States** | the P1 machine unchanged: CANDIDATE → CONFIRMED → SUPERSEDED / RETRACTED / EXPIRED. `inferred`/`explicit` is the **origin**, EXTRACTED/INFERRED/AMBIGUOUS the relation **tier** — neither is a state. Every model-derived item is CANDIDATE + inferred. |
| **Provenance** | `source_kind` (inspection / import / execution / user), `source_ref` (the inspection, meeting, mission or feedback), `observed_at`, `route_decision_id` (→ harness, account, model, candidates), `context_package_id` (what the call was shown), `anchors` (module paths). `confidence` exists and is never filled by P6: no pass asks a model for one, and none would count (D4). |
| **Relations** | `depends_on`/`uses`/`contains`/`calls`/`implements` between entities of one answer (INFERRED); `contradicts` from a new item only to a knowledge item **in the call's ContextPackage** (INFERRED; a relation, never a state change — P5's constraint conflicts stay separate and need no relation); `decided_in` (DECISION → meeting), `learned_from` (LESSON → mission), `supersedes` — EXTRACTED, because those links are facts. A relation whose end the answer did not describe is dropped and counted (the permitted partial result). |
| **Supersession** | `confirm` of an item with `supersedes_id` moves the older (which must be CONFIRMED) to SUPERSEDED with `valid_until` and `superseded_by_id`, in one transaction; the user's `supersede` creates the replacement with origin explicit, which confirms itself. Chains are kept whole (`get_knowledge.chain`). |
| **Retraction, forget** | `reject` (CANDIDATE), `retract` (CONFIRMED); `forget(selector, mode, dry_run=True)`: `retract` keeps the row, `purge` blanks title/text/anchors/constraint and keeps a tombstone with its provenance (`knowledge_item.purged`). A dry run changes nothing. |
| **Expiry** | the edge exists; P6 has no automatic decay (§2). |
| **Staleness** | a CONFIRMED item read from an inspection is labelled stale by P5 when its repository has moved past that inspection's revision (revision-level: an item cites its inspection, not the files the model read). |
| **Identity** | `key(title)`: casefolded, whitespace collapsed — **equality, never similarity**. An entity or lesson already live under the same key and scope is not created twice. |

## 7. The passes

| pass | trigger (knowledge worker, an outbox consumer) | schema | produces | once |
|---|---|---|---|---|
| knowledge (D6) | a project's first COMPLETED inspection | `knowledge.v1` | ENTITY candidates, relations, `contradicts` | per project |
| decisions | `meeting.imported` | `decisions.v1` | DECISION candidates, `decided_in` | per meeting |
| lessons | a mission COMPLETED or FAILED | `lessons.v1` | LESSON candidates, `learned_from`, corroboration | per mission |

"Once" is read from the RouteDecisions: a source whose pass ended `ok` or `invalid` is not passed
again by its trigger, so a re-delivered event learns nothing twice. A pass that failed for a reason
outside the answer runs again only if its event is delivered again (a crash); a `gated` pass runs
again when the user permits headless use (`provider_terms.decided`). A call left open by a dead
Core is ended `failed (core_restarted)` by the worker's boot sweep. A result that cannot be
recorded rolls back and ends its call `failed`; a pass that raises is its event's recorded error,
never the worker's death.

**D6 (accepted):** the knowledge pass is the model pass (today's legacy memory building); the
deterministic facts stay P4 state, which P5 already reads at L1 — no second copy. **D4
(accepted):** a LESSON confirms itself when `learned_from` links it to **2 distinct missions**
(`CORROBORATION`); nothing else promotes a model's output.

**K3 / project setup.** A project is usable from its deterministic assessment. `status()` reports
each project's `knowledge_pass` (`queued` → the latest RouteDecision's outcome: `ok`, `failed`,
`gated`, …, with `items` as a **count**); nothing else about the project depends on it.

## 8. Meetings, feedback, context

- **Meeting import:** `read_notes` takes the date from the file name or its first lines and
  **refuses** a file with neither (§8's "or asked" is P7's); the name is the first `# ` heading.
  Notes are an artifact; importing the same notes into the same scope again returns the meeting.
- **Feedback (§7.8):** history; `promote` is the explicit step that creates a CANDIDATE PREFERENCE
  or LESSON, optionally superseding a CONFIRMED item once it is confirmed. **D1 (accepted):** S9
  moves to P7, because only intent can decide that a message is feedback.
- **Context (D7, accepted):** meetings in scope are L2 candidates (S8); relations are stored but
  1–2-hop expansion and the `link` input are P7's; no weight changed.

## 9. Routes

| Route | Scope | Idempotency |
|---|---|---|
| `GET /v1/knowledge?project&state&type`, `GET /v1/knowledge/{id}` | observe | — |
| `POST /v1/knowledge/{id}/confirm`, `/reject`, `/retract`, `/supersede` | control | required |
| `POST /v1/knowledge/forget` (dry run unless `dry_run: false`) | control | required |
| `POST /v1/feedback` | control | required |
| `POST /v1/meetings/import` | **admin** (it reads a file on this machine; P4 D7's reasoning) | required |
| `GET /v1/route-decisions?source&purpose`, `GET /v1/route-decisions/{id}` | observe | — |
| `GET /v1/provider-terms`, `POST /v1/provider-terms/{harness}` | observe / **admin** | — / required |

`/v1/health` gains `knowledge: {state, pending}` (pending = events the worker has not consumed),
which the HTTP judge's idle signal reads. **D8:** `CoreClient` gains `list_knowledge`; P6
implements `import_meeting` and `route_why` (a RouteDecision id, or the latest decision about a
source id) in both bindings.

## 10. Acceptance scenarios

| # | Test | Phase |
|---|---|---|
| S8 | `test_s08_meeting_context.py` — imported notes are cited by a mission's package, with a reason (both bindings) | P5–P6, **passes** |
| S9 | re-tagged `phase:P7` (D1) | P7 |
| K1 | `test_k01_knowledge_without_claude.py` — fake `headless` harnesses only; `headless`-less never elected; nothing capable → `unavailable`; your choice and model honoured; a missing choice falls back and drops its model; the router function stays `phase:P10` | P6, P10 |
| K2 | `test_k02_structured_extraction.py` — native and prompted both valid; invalid retried once then accepted; invalid twice → no knowledge; provenance names harness and model | P6 |
| K3 | `test_k03_project_setup.py` — success counted, failure and gated never fail the project, a model's "done" is not knowledge | P6 |
| L01–L16 | `tests/v1/unit/test_knowledge_units.py` — election, gate exemption by class, vocabulary, the legacy preference, explanation, identity, Core checks, both mechanisms, the parse seam, the real adapters' argv against a stand-in runner, error names, import boundaries | P6 |
| N01–N24 | `tests/v1/integration/test_knowledge.py` — gate never calls a real adapter, re-run on permission, re-check before spawn, only the user answers, a real adapter end-to-end with a stand-in runner, provenance, no execution, usage, relations and drops, `contradicts`, redelivery, re-run, one initial pass, every failure named, record failure rolls back, boot sweep, supersession chains, forget and purge, feedback, meetings, undated notes, corroboration over three real missions | P6 |
| N30–N33 | `tests/v1/integration/test_knowledge_http.py` — terms routes, meeting import refusals, lifecycle and forget over HTTP, `archeus terms` | P6 |

## 11. Legacy seams (migration-plan §3)

`claude_sessions/llmcall.py` gains `parse_json`, `unwrap_structured` and `budget_args`, moved
unchanged out of `memory.py`, which imports them back; the claude_code adapter parses with the
same code the current product does. `claude_sessions/cli.py`'s `V1_VERBS` gains `terms`. P5's
lexical seam and its import closure are untouched; P6's own path is checked to reach no
`memory`, `recall`, UI or router (L16).

## 12. Deviations from the architecture documents

1. **S9's phase is P7** (testing-strategy §2 changed, D1): its judge drives `submit_message`,
   and classifying a message is intent. The CANDIDATE-vs-auto-confirm tension between S9 and
   §3's "explicit statements auto-confirm" is left for P7, where it can be decided per intent.
2. **No Decision rows in P6** (D9): a decision from notes is a candidate DECISION item; the
   mirror of a made decision is P7's.
3. **Inspection facts are not materialised as knowledge** (D6): §3's "repository inspection →
   FACT/ENTITY, auto-confirm when EXTRACTED" would copy P4 state; only the model pass writes items.
4. **No relation expansion in context** (D7), no consolidation, backup → verify → swap or usage
   decay (§2: P14/P7+), no Person links for attendees, no model-offer validation before P10, and
   the legacy own-call provider profile is not honoured by the V1 claude_code adapter (P10).
5. **"Retry once, then ask"** ends the call `invalid` after the retry; there is no asking surface
   before P7/P16.

## 13. Known limitations

- A pass that failed for a transient reason (timeout, no harness) is not retried on a schedule;
  it runs again only on redelivery or, if gated, when the terms change. Scheduling is P14.
- Staleness of model-derived items is revision-level.
- `archeus terms` needs a running Core (the answer is a Core row, recorded with its event).

## 14. Decision pass

| # | Decision | Outcome |
|---|---|---|
| D1 | S9 → P7; P6 builds feedback promotion and explicit supersession | **accepted** |
| D2 | Core-held per-harness ProviderTerms, `unknown` blocks, only the user answers, re-checked before the spawn, fakes exempt by class | **accepted** |
| D3 | Build claude_code + pi `call()` now, gated; Codex not headless | **accepted** |
| D4 | Lessons: corroboration by 2 distinct missions only; confidence never promotes | **accepted** |
| D5 | Own-call preference from the legacy settings through a port until P22 | **accepted** |
| D6 | Knowledge pass = the model pass; deterministic facts stay P4 state | **accepted** |
| D7 | Relations stored, expansion deferred; meetings as L2 candidates | **accepted** |
| D8 | CoreClient `list_knowledge`; `import_meeting`, `route_why` implemented | contract addition (testing-strategy §1.1 first) |
| D9 | No Decision persistence in P6 | follows D1 (decisions are made in conversation) |
| D10 | RouteDecision before the call, outcome once, usage against it | ADR-0022, domain-model §8.5–§8.6 |
| D11 | The gate is an election step, so another eligible harness may be elected | a preference is not a constraint (resource-router §3) |
| D12 | Invalid → retry once → `invalid` | ADR-0006, minus the P7 ask |
| D13 | One initial pass per project; gated passes re-run on permission | plan P6 ("first COMPLETED inspection") |
| D14 | Revision-level staleness | the item cites its inspection |
| D15 | Calls not about a repository run in ARCHEUS_HOME | read-only, and no repository to read |
| D16 | Undated notes refused | §8 ("or asked" is P7's) |
| D17 | `parse_json`, `unwrap_structured`, `budget_args` move to `llmcall` | the P0.5 seam principle |
| D18 | `archeus terms` | D2 said "route + CLI" |

**DESIGN_GATE = IMPLEMENTED.**
