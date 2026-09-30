# P5 design gate: the context engine

Status: **IMPLEMENTED (P5).** Written 2026-09-25 against `c611b70` (P4 closed; main 2.8.0 merged
into V1 with the ADR-0022/0023 parity amendments). The decision pass accepted D1–D4 as
recommended (§10); D5–D10 follow from the documents' own precedence rules and are recorded here
rather than asked.

Sources read, and precedence: the plan (§9, §31.1 **P5**, P6, P7), ADR-0012, ADR-0013,
ADR-0022, ADR-0023, context-and-knowledge **§1–§2** and §5, domain-model §5 and §7.1,
state-machines §2 and §11, api-and-realtime §2 (the Context row), testing-strategy §1–§3 (row
**G2**, S8), target-architecture (package layout), migration-plan §2.4 and §3, the P4 design
gate §7 and §16, and the code: `archeus/core/{engine.py,application,domain,world}`,
`archeus/api/*`, `archeus/infra/{db,eventlog}`, the judge (`test_g02_context_package.py`,
`test_s08_meeting_context.py`, `client.py`, `http.py`), and `claude_sessions/recall.py`. Where a
document and the code disagree the code states what exists; where two documents disagree the more
specific one wins, and the executable judge (frozen in P1) is the most specific of all.

---

## 1. What P5 is

Given a subject — a mission in CONTEXT_GATHERING, or a project with a query — decide which
existing information is relevant, at which level, and why, and return a bounded, deterministic,
explainable package. It is read-only infrastructure: no model, no harness, no router, no
execution, no learning, no knowledge write. The only thing it writes is the package itself, once,
in the mission's `context_ready` move.

**What exists to select from in P5.** Current state: the mission, its project, the project's
repositories, their latest completed inspection and their drift assessment (all P4). Knowledge:
`knowledge_items` — in practice the ARCHITECTURE constraints P4 lets a user declare, plus
whatever a later phase writes. History: the project's user-visible events. There are no
relations, meetings, people, lessons or anchors yet (P6), no tasks at CONTEXT_GATHERING (the
plan does not exist yet), and no mission `context_scope` field (nothing sets it before intent,
P7). The engine is written for the whole of §2 and fills the levels that have data; the rest
are empty, never faked.

## 2. Boundaries

| | |
|---|---|
| **P5 owns** | `archeus/core/context/` (`levels.py` — levels, shares, weights, authority, windows; `assemble.py` — gather, score, conflicts, budget), `archeus/infra/search/bm25.py`, the `ContextPackage` entity and table, the `context_ready` command, the engine's CONTEXT_GATHERING step, `GET /v1/context/{id}`, `POST /v1/context/preview`, `Mission.context_package_id` |
| **P5 consumes** | P4's projects, repositories, inspections, findings and knowledge rows; the event log; the legacy BM25 through the new `claude_sessions/lexical.py` seam |
| **defers to P6** | relations and relationship expansion (the `link` term), confidence and usage signals (`conf`, `useless`), `stale_after` on knowledge, supersession writes, prose contradiction (`contradicts`), meetings (S8), lessons, the knowledge pass |
| **defers to P7** | `Mission.context_scope` (pins, excludes, levels — set by intent), anchors from a task's files (`anchor`), `assumptions`, rendering the package for the brain (and the rendered artifact), passing the package to `brain.calls` |
| **defers to P11/P12** | linking a package from an execution and a checkpoint's `relevant_context_refs`; re-assembly per execution |
| **defers to P16** | the *Why* tab that renders reasons and exclusions |
| **never** | a model call, a harness adapter, the Resource Router, a subprocess, a mutation of any row other than the package insert and the mission move |

## 3. The package (D5: the judge's shape)

§2.3's YAML is an illustration; the G2 judge (frozen in P1) is the contract, and they disagree in
two places: the judge reads `items[].source_kind` and `budget.{limit_tokens, used_tokens}`,
§2.3 wrote `source: {kind, …}` and `budget_tokens`. The judge wins; §2.3 is corrected in place.

```yaml
id: ctx_…                          # absent from a preview
subject_kind: mission | project
subject_id: msn_…
workspace_id, project_id
as_of_seq: 812                     # the last event in the snapshot
as_of_at: 2026-09-25T10:00:00.000Z # its time: the engine's "now"
query: "…"                         # mission title + objective, or the preview's query
levels: [L0, L1, L2, L3, L4]
budget: {limit_tokens: 12000, used_tokens: 820,
         levels: {L0: {limit_tokens, used_tokens}, …}}
scoring: {weights, authority, recency_window_days}
items:
  - ref: {kind: repository_inspection, id: rin_…, version: 3}   # events: {kind: event, id, seq}
    level: L1
    store: state                   # state | knowledge | history
    type: INSPECTION               # MISSION PROJECT INSPECTION DRIFT, a knowledge type, an event type
    source_kind: repository_inspection
    source_ref: rin_…
    observed_at: …
    freshness: current             # current | stale  (superseded is never an item)
    relevance: 1.94
    signals: {lex, anchor, link, rec, auth, conf, stale, useless}
    reason: "latest completed inspection of D:/x at 3f2a…; matches api, core"
    tokens: 60
    conflicts_with: []
excluded:  [{ref, level, freshness, reason}]
conflicts: [{items: [older, newer], preferred: newer, kind, reason}]
assumptions: []                    # P7
missing_information: ["D:/x has no completed inspection"]
```

Items are **references**, never copies: the text an item stands for is read to score and count
it, and not stored (D2). `ref.version` names the exact row version that was read, so a later
reader can tell whether what it points at has moved since.

## 4. Persistence (D2)

Migration `0004_context.sql`: `context_packages (id, workspace_id, project_id, subject_kind,
subject_id, <meta>, body)`, indexed by subject. `ContextPackage` has no state machine and no
command that edits it; the one constructor is in `Missions.context_ready`. It is recorded with
one event, `context_package.created` (visibility `system`: it is not news for the digest), in the
same transaction as the mission's `context_ready` move, which also sets
`Mission.context_package_id`. A preview is never persisted, and no rendered text or artifact is
written in P5: the rendering belongs to its first consumer, the P7 brain call.

**The package is assembled inside the writer transaction** from that transaction's own snapshot,
so it states exactly what the rows said when it was recorded; there is no read-then-write race
to lose.

## 5. Selection

### 5.1 Candidates (gather)

| Level | Store | Candidate | Authority |
|---|---|---|---|
| L0 | state | the mission (title, objective, criteria) | explicit |
| L1 | state | the project (state, each repository's kind, branch, architecture state, revision) | explicit |
| L1 | state | each repository's latest COMPLETED inspection (languages, frameworks, commands, docs, agent config) | extracted |
| L1 | state | each repository with violated findings: the open blockers | extracted |
| L1 | knowledge | CONFIRMED items of this project, except LESSON (L3) and PREFERENCE (L4) | explicit if `origin=explicit`, else confirmed for ARCHITECTURE/DECISION/STANDARD, else inferred |
| L2 | — | nothing in P5 (relations, related projects, people, meetings are P6) | — |
| L3 | history | the project's user-visible events in the 7 days before `as_of_at`, newest 50, excluding the subject's own | extracted |
| L4 | knowledge | CONFIRMED items with no project, in the subject's or the global workspace | as L1 |

Out of scope is never a candidate (another project's items). In scope but not usable is
**excluded with the reason**: SUPERSEDED (`superseded by kno_…` when the superseding item is
known), RETRACTED, EXPIRED, CANDIDATE. A repository whose `architecture_state` is STALE labels
its inspection and drift items `stale`. A repository with no completed inspection, a project
with none registered, and a mission with no project are **stated gaps** in
`missing_information`.

### 5.2 Relevance (D1: formula + weight table)

`score = Σ w·signal`, with `stale` and `useless` subtracted, over every term of §2.2:

| term | weight | input in P5 |
|---|---|---|
| lex | 1.0 | BM25 of the query over the candidates' text, divided by the best candidate's (0–1) |
| anchor | 0 | none until tasks name files |
| link | 0 | none until relations (P6) |
| rec | 0.5 | `max(0, 1 − age / 7 days)`, age measured from `as_of_at` |
| auth | 1.0 | the authority table of §2.2: explicit 1.0, confirmed 0.9, extracted 0.8, inferred 0.5, candidate 0.3 |
| conf | 0 | none until confidence (P6) |
| stale | 0.5 | 1 when stale |
| useless | 0 | none until usage signals (P6) |

The weights are the whole of the tuning, in `levels.WEIGHTS`, and are recorded in every package's
`scoring`. A later phase adds a term's **input**; it does not add a second ranker. The recency
horizon is §2.2's own 7-day temporal window, not a new constant.

### 5.3 Conflicts (D4: checkable constraints only)

Two CONFIRMED in-scope items conflict when their constraints cannot both hold:

- `framework_pinned` of the same package to two different versions (an unpinned version is
  compatible with any pin);
- two `require_layering` constraints that order the same two layers oppositely.

Every other pair among the existing kinds can hold together: `forbid_dependency` and
`require_layering` are both prohibitions, and `module_exists`/`doc_matches_code` constrain no
ordering. There is no `require_dependency` kind, and P5 adds none. The newer item (later
`created_at`, then id) is preferred; the older stays in the package with `conflicts_with` and a
reason saying so. **Nothing changes state**: moving the older item to SUPERSEDED is a knowledge
write, which is P6's supersession, never the context engine's. Prose is never compared.

### 5.4 Budget and order

Token estimate: `lexical.tokens_estimate` (chars/4, the legacy estimator). Default limit 12000
(§2.3), per-level shares 40/30/15/10/5, filled L0 → L4. A level's quota is its share plus
whatever the level above left unused; a level out of scope passes its whole quota down and its
candidates are excluded as `level Ln is not in scope`. Within a level, candidates are taken
greedily by `(−relevance, ref kind, ref id)`: one that does not fit is excluded with `over the Ln
budget: needs N tokens, M left` and a smaller one after it may still fit. So `used ≤ limit`
always, and historical or global information can never displace immediate context: L0 is filled
first and only its leftovers flow down.

Items are listed by level, then store (state → knowledge → history, §1), then the same key.

### 5.5 Determinism

"Now" is `as_of_at`, the time of the snapshot's last event — never the clock. Weights, shares
and windows are constants; ties break on the stable id; floats are rounded to six places. The same
rows and the same request therefore give the same package, byte for byte, apart from the
recorded package's `id`. No digest is computed: none is specified, and the package id plus
`as_of_seq` identify one.

## 6. Routes

| Route | Scope | Idempotency | Does |
|---|---|---|---|
| `GET /v1/context/{id}` | observe | — | a recorded package (404 when unknown) |
| `POST /v1/context/preview` | observe | none (writes nothing) | `{subject: {kind, id}, query?, levels?, limit_tokens?}` → an unrecorded package |

`GET /v1/missions/{id}` carries `context_package` (the recorded package, or null). No
`CoreClient` operation was added: G2 reads the package through `get_mission`.

## 7. Legacy seam (D3)

`claude_sessions/lexical.py` (new, stdlib only): `tokens_estimate`, `tokenize`, `STOPWORDS`,
`query_tokens`, `idf`, `bm25`, `BM25_K1`, `BM25_B` — moved unchanged out of `recall.py`, which
imports every name back (`_tokenize`, `_bm25`, `_idf`), so its behaviour and its callers are
unchanged. `archeus/infra/search/bm25.py` wraps it. The P0.5 principle: `recall` imports `memory`
at module level, so reusing `recall` directly would put the headless model call inside the
context engine's import closure.

## 8. Engine integration

CONTEXT_GATHERING leaves `engine.STUB_STEPS`; the engine runs `Missions.context_ready`, which
assembles, records and fires `context_ready` (unguarded, as the P1 table has it) in one
command. The trigger stays fireable by name through `Missions.fire` (as the lifecycle tests do),
which moves the mission without a package: making the edge require one would be a P3 state-table
change nothing in P5 needs, and is left for the phase that has a second caller.

## 9. Acceptance scenarios

| # | Scenario | Test |
|---|---|---|
| G2 | every item has a reason and a source; used ≤ limit (both bindings) | `tests/v1/judge/test_g02_context_package.py` |
| C01 | each level gets its share; unused budget flows down | `test_context_units.py` |
| C02 | over budget → excluded with the reason; a smaller item still fits; exact fit fits | units |
| C03 | provenance: ref, level, store, source kind/ref, observed_at, reason, matched words | units |
| C04 | superseded (with the superseding id), retracted, expired, candidate excluded with reasons | `test_context.py` |
| C05 | a stale item is labelled and ranked exactly `w_stale` below its fresh twin | units, integration |
| C06 | conflicting pins/layerings detected, newer preferred; compatible pairs and prose not | units, integration |
| C07 | order: level → store → relevance → id, for any input order | units |
| C08 | no candidates → a valid empty package | units |
| C09 | a disabled level is excluded and passes its budget on | units |
| C10 | relevance is the weighted formula with every term present | units |
| C11 | the same snapshot gives the same package | integration |
| C12 | assembling writes nothing (every table and the event log unchanged) | integration |
| C13 | `context_ready` records one immutable package linked from the mission; nothing outside CONTEXT_GATHERING; no edit path exists | integration |
| C14 | P4's project, inspection and drift at L1; STALE labels both; a never-inspected repository is a stated gap | integration |
| C15 | preview writes nothing; a recorded package is readable; 404 and 400 | integration (HTTP) |
| C16 | the context path's import closure has no memory, llmcall, recall, harness, engine, runtime or subprocess | units |
| C17 | recall's lexical names ARE lexical's; lexical imports stdlib only; no second BM25 | units |
| C18 | recent project events are L3 history; older ones and the subject's own are not | integration |

Mutation-verified (15/15 killed): the stale penalty's sign, the stale weight, the budget fit
(`<` for `<=`), flow-down, superseded and candidate exclusion, both conflict rules, the id
tie-break, store order, stale labelling, the history window, the engine stub, a `recall` import
in the search wrapper, and a preview that writes.

## 10. Decision pass

| # | Decision | Outcome |
|---|---|---|
| D1 | Ranking: §2.2's formula with a weight table (lex 1.0, auth 1.0, rec 0.5, stale 0.5, the rest 0), ties by id | **accepted** |
| D2 | Persistence: an immutable `context_packages` row + `context_package.created`, linked by `Mission.context_package_id` in the `context_ready` move; no rendered artifact until P7 | **accepted** (§2.3 said "artifact + row"; corrected in place) |
| D3 | BM25 reuse through a new model-free `claude_sessions/lexical.py`; `recall` imports it back; an import-closure test | **accepted** |
| D4 | Conflicts: checkable constraints only; newer preferred, older flagged in the package; no prose comparison | **accepted** |
| D5 | The judge's package shape over §2.3's illustration | precedence rule (the judge is frozen and executable) |
| D6 | Items are references with row versions, never copies of text | follows D2 and "references where the domain model specifies them" |
| D7 | "Now" is the snapshot's last event, not the clock | the only way §2.2's recency term is deterministic |
| D8 | L3 temporal candidates: 7 days (§2.2), newest 50 (a retrieval bound; the budget decides inclusion) | the one new constant; it bounds work, not ranking |
| D9 | No `Mission.context_scope` in P5; the preview takes `levels` | nothing sets a scope before intent (P7) |
| D10 | Preview is `observe` and takes no idempotency key | it writes nothing |

**DESIGN_GATE = IMPLEMENTED.**
