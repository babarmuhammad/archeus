# P4 design gate: world model, repository inspection, drift, status and digest

Status: **IMPLEMENTED (P4).** Written 2026-09-25 against `f9561f8` (P3.5b closed: `883d227` + the
blocker fixes; the P3.5a recycled-PID fix `f4bfc2a` inside it). The decision pass accepted D1–D7
and D8 with a constraint: `.archeus/connections-cache.json` is derived, non-authoritative state
that nothing reads back; the world model and the persisted inspections are the authority.

**Where the implementation departs from this text, and why** (the sections below are corrected
in place; this list is the record):
- **The assessment lives on the Repository, not on an inspection.** An inspection row is an
  observation — unique per (repository, revision, extractor version), never edited after
  COMPLETED. The drift result is current state: `Repository.findings`, `evaluated_against` (the
  constraint-set token) and `evaluated_constraints` (knowledge item id, version), written only by
  the guarded `architecture` edges. So a re-evaluation after a new constraint (W12) creates no
  second inspection row, and "one COMPLETED inspection per repository + revision + extractor"
  holds literally. The commands are `begin_inspection`, `complete_inspection`,
  `fail_inspection`, `record_assessment` and `sweep_inspections`.
- **Event names follow the writer.** `Tx.transition()` names an event `<machine>.state_changed`,
  so the design's `repository.architecture_changed`, `knowledge.created` and
  `knowledge.state_changed` are `architecture.state_changed`, `knowledge_item.created` and
  `knowledge_item.state_changed`. Visibility is per type, so every architecture move is
  user-visible and the digest, not the registry, drops the moves into STALE.
- **The owner's `users` row is written by the first acknowledgement**, not by a bootstrap:
  before it, the cursor is 0. No eighth event type was needed.
- **A retry-capped revision waits for HEAD to move.** A walk that failed three counted times
  is not retried when a constraint changes: the failure is the walk's, and a constraint does not
  change what can be walked.
- **Discovery runs inside `create_project`**, so an idempotent replay is a replay: the key's
  hash covers the request (name, roots), never what the filesystem said.
- **Two additive P2/P3.5b changes.** `Tx.update()` writes non-state fields (the User cursor has
  no state machine), refusing the id and the state field and still requiring an event. The error
  table gains `409 conflict` (a repository already registered).
- **`KnowledgeItem.body` is `text`**: `body` is the row codec's JSON column, the one clash the
  P2 schema test had recorded for the phase that would persist knowledge.
- **An extractor upgrade does not by itself re-inspect a current assessment.** Re-walking the
  same revision would need an `architecture` edge out of CONSISTENT/DRIFTED that D5 does not
  have, so a current assessment stays current across an upgrade, and the next HEAD move or
  constraint change walks again with the new extractor — the old extractor's observation is never
  re-evaluated. A fifth edge (`extractor_changed` → STALE) is the alternative, left for a
  decision; `test_an_extractor_upgrade_is_used_by_the_next_assessment_never_an_old_observation`
  pins the behaviour either way.
- **The fixtures are `tests/v1/fixtures/repos/<name>/`** (the path the rig declared in P1).
- **Manifests read:** `pyproject.toml` (one regex parser on every Python, since 3.10 has no
  `tomllib`), `requirements*.txt`, `package.json`, `Cargo.toml`, `go.mod`; `*.csproj` is not
  read in P4.
- **A lingering close on the 413 path** (a separate commit): the one refusal that leaves a body
  unread by design — over 1 MiB, or a malformed `Content-Length` — now drains it, bounded
  (2 s, 16 MiB), after answering. It is the P3.5b unread-body race on the path the P3.5b fix could
  not read first, and P4's extra thread made it reproducible under a full run.

Sources read, and precedence: the plan (§31.1 P3.5 "as built", **P4**, P5–P13, §31.2, §31.3,
§31.4), ADR-0001/0002/0004/0006/0009/0012/0013/0019/**0021**, context-and-knowledge **§6 and
§9**, state-machines **§10** (architecture) and §11 (knowledge), domain-model §3.1, **§4**, §5,
api-and-realtime §1–§2, migration-plan §2 (reuse table) and §3 (seams), testing-strategy §1.1
and §2 (rows S7, S13, S14), target-architecture (package layout), the P3.5b design gate, and the
code: `archeus/core/{domain,application,engine.py,runtime.py,ports.py}`, `archeus/api/*`,
`archeus/infra/db/{rows.py,migrations}`, the judge (`tests/v1/judge/{client,http,support,
conftest}.py`, `test_s07_drift.py`, `test_s13_status.py`, `test_s14_digest.py`), and the legacy
modules P4 reuses (`claude_sessions/repos.py`, `claude_sessions/connections.py`). Where a
document and the code disagree the code states what exists; where two documents disagree the
more specific one wins and the conflict is listed in §1.3.

---

## 1. What P4 is

### 1.1 The answer in one paragraph

P4 is the **OBSERVE → UNDERSTAND** half of the operating model for the *world*, done
deterministically. Core learns which projects and repositories exist, inspects each repository
at its HEAD revision without any model (languages, manifests, commands, agent config, the
import graph), notices when HEAD moves, checks the result against architecture constraints the
user declared, and answers two questions without a brain: **"what is the state across my
projects?"** (S13, deterministic part) and **"what changed while I was away?"** (S14, one
device). It establishes the world tables, the inspection record that P5 (context), P6
(knowledge) and P13 (CodeVerifier's `test_commands`/`build_commands`) read, the per-user digest
cursor, and a Core-side world worker. It makes **no model call of any kind** (§2).

### 1.2 The plan is right; the brief is not P4

The brief for this gate describes a Mission → Plan → Task → Resource → Execution → Verification
→ Review vertical slice with a controlled real model call. **That is not P4.** In the dependency
order the plan fixes (§31.3, `P35 --> P4 --> … --> P13`) and the repository confirms, those boxes
belong to:

| Box in the brief | Owner phase | Where it stands today |
|---|---|---|
| Intent → mission | P7 (`missions/intent.py`, grammar) | `create_mission` is a command, no intent parsing (P3.5) |
| Context gathering | P5 (context engine, G2) | none; P4 produces the inspection P5 reads |
| Knowledge beyond constraints | P6 | only the constraint slice (D3) moves into P4 |
| Plan / task graph / replan | P7 brain, P8 plan engine (DAG, `touches`, versioning) | `ScriptedBrain`/`FixedPlanBrain` stubs; P3 lifecycle, supersession guards |
| Policy authorization | P9 | `AllowAllPolicy` stub; the adapter registry refuses real adapters |
| Resource selection / accounts | P10 (router); pre-router brain calls P7 (legacy `rotate.elect()`) | `FixedCandidateRouter` stub |
| Execution manager, real harness, process registry | P11 | fake harness, boot sweep, recycled-PID-safe reconcile (P3.5) |
| Checkpoint / hand-off | P12 | none |
| Verification / review | P13 | `AutoPassVerifier`/`AutoAcceptReview`/scripted stubs; P3 guards make completion require both |
| Learning pass | P6 (consumer), P13 (after COMPLETED) | none |

P4 changes none of that path except **project scoping**: `create_mission(project_id=…)` starts
validating the project, and `list_missions(project_id=…)` starts filtering (both declared "arrives
with projects (P4)" in the judge). The mission lifecycle invariant — *a mission is not complete
because an execution says done; completion needs verification and review* — is untouched and
stays enforced by the P3 table guards.

Operating-model ownership: **P4 owns OBSERVE and UNDERSTAND for code and projects, and the
UPDATE STATE of world objects.** REASON/SUGGEST (P7), PLAN (P8), ASK/APPROVE (P9), ACT (P11),
VERIFY (P13), LEARN (P6/P13) are not P4.

### 1.3 Conflicts found between the documents and the repository

| # | Conflict | Correction proposed |
|---|---|---|
| C1 | Drift is checked against "CONFIRMED ARCHITECTURE / DECISION knowledge items" (context-and-knowledge §6, state-machines §10), but `knowledge/*` is P6 and P4 precedes it; no `knowledge_items` table exists | **D3**: P4 creates the `knowledge_items` table and exactly one write path — a user-declared ARCHITECTURE item carrying a checkable constraint, auto-confirmed because `origin = explicit` (state-machines §11 `confirm`). Everything else about knowledge stays P6 |
| C2 | The judge's rig must register a fixture repo and its constraint "using a CoreClient, never Core internals" (support.py), but the frozen `CoreClient` has no project or constraint operation (testing-strategy §1.1: "exactly the operations the scenarios use") | **D1**: add `create_project` and `declare_constraint` to the protocol — the two operations S7 cannot be written without. `testing-strategy §1.1` and `test_core_client.py`'s DOCUMENTED set change with it |
| C3 | api-and-realtime §2 puts the digest inside `/v1/now` + `/v1/now/ack`; the P3.5b gate defers `/v1/now` to P16; S14's P4 function needs the digest now | **D4**: `GET /v1/digest` + `POST /v1/digest/ack` in P4; P16's `/v1/now` embeds the same query; `/v1/now/ack` is dropped in favour of `/v1/digest/ack` |
| C4 | The `architecture` machine cannot express four real situations: a first inspection that already violates a constraint (no `UNKNOWN → DRIFTED`); a fix commit on a drifted repo (no edge out of DRIFTED on a new revision); a constraint declared on an inspected repo (no edge for "constraints changed"); and so a drifted repo could only ever leave DRIFTED through the P6 resolution | **D5**: four additive edges (§5); state-machines.md changes with them (it is pinned by `test_state_tables.py`) |
| C5 | Entities are P1 stubs: `RepositoryInspection` has 3 of domain-model's ~13 fields, `Repository` lacks `last_inspection_id`, `User` lacks `last_ack_event_seq`, `KnowledgeItem` has no structured constraint; no world or user table exists | the migration and field additions of §4 (additive; no existing column changes) |
| C6 | ADR-0021 says the gate falls before "the first tool-less structured call in P4, P6 or P7"; the plan makes P4's model pass optional with the deterministic pass sufficient | **D2**: P4 ships no model pass; the ADR text drops "P4" |
| C7 | `missions.project_id` has no foreign key and P3.5b accepted any string for it | validate in the application layer from P4 on (SQLite cannot add an FK without a table rebuild, and a rebuild for this is not worth it); a pre-P4 row with an unknown `project_id` is reported by `status()` under `unknown_project` rather than rejected |

---

## 2. Model calls and the provider-terms gate (ADR-0021)

- **P4 makes zero real model calls** (D2). Of the three classes in plan §31.4, P4 uses only the
  first (fake/scripted) and even that only through the existing mission path; the world code
  calls no model at all. The optional "model pass" of inspection (context-and-knowledge §6 step
  4: module summaries and INFERRED edges — today's `memory` unit extraction) is **deferred to
  P6**, where its output (ENTITY/FACT knowledge) has a home. The plan already requires that "the
  deterministic pass alone must satisfy the acceptance", so nothing in P4's acceptance needs it.
- **Where the gate moves.** The first real headless call becomes the first of P6's
  decision-candidate extraction or P7's brain, whichever is enabled first; the gate is passed
  **before the code path that makes that call is switched on**, not before the phase starts —
  both phases develop and pass acceptance on the scripted brain and recorded fixtures (plan P6,
  P7). ADR-0021 stays OPEN through P4 and is not a P4 blocker.
- **If subscription automation is not permitted:** nothing in P4 changes — P4 has no account.
  For later phases the rule of §31.4 stands: the same architecture runs on API-key/provider
  accounts, recorded as Account rows with a different `auth_kind`; the router (P10) and the
  pre-router shim (P7) select among whatever accounts are allowed, so no redesign follows.
- **Guard.** A P4 structural test asserts that no `archeus/core/world/` module imports
  `claude_sessions.llmcall`, `claude_sessions.memory`, `claude_sessions.rotate`,
  `claude_sessions.quota` or `archeus/core/brain`, and the suite's existing `conftest.py` guard
  still refuses any spawned `claude`. `git` is the only process P4 may spawn (§6.2), and only as
  a fallback.
- **Resource selection in P4: none.** There is no model call, so there is no account to choose,
  no usage to record, no ceiling to respect and no RouteDecision to write. P4 does **not** touch
  `rotate.elect()`/`quota.reason()`; that shim is P7's (plan P7), recorded as a pre-router
  RouteDecision so P10 can replace it without rewriting P7.

---

## 3. Contracts P4 consumes, and contracts it establishes

### 3.1 Consumed (frozen, not modified)

| Contract | From | Used for |
|---|---|---|
| single writer, one transaction per command, `VersionConflict`, idempotency keys | P2 | every world write |
| entity codec (`rows.py`: promoted columns + JSON body, `TABLES`) | P2 | the new tables |
| transactional outbox, `events_after`, retention, `CursorExpired` | P2 | the digest, SSE delivery of world events |
| `TransitionProof` / table-driven machines (`states.py`, `guards.py`) | P3 | inspection and architecture transitions |
| route table + schemas, the §4 request pipeline, coarse scopes, error table (§5.5) | P3.5b | the P4 routes |
| SSE (ids only, `seq > cursor`) | P3.5b | world events reach the SPA with no new stream code |
| Core runtime lifecycle (lock → db → token → engine → HTTP → `core.json`), boot sweep, exit codes | P3.5b | the world worker starts after the engine and stops before it |
| writer commit notification | P3.5b | the worker wakes on `create_project` / `declare_constraint` |
| judge bindings (`InProcessClient`, `HttpClient`), `support.idle`, `wait_for` | P1 / P3.5b | S7, S13, S14 on both bindings |
| `repos.find_git_repos` + `classify` (depth 4; submodule and worktree by the gitdir line) | legacy, REUSE AS-IS (migration-plan §2) | repository discovery |
| `connections.build_hierarchy` (Python AST + C/C#/JS/TS regex import graph, caps) | legacy, REUSE AS-IS | the module graph (§6.3 lists the four properties the design must work around) |

### 3.2 Established by P4

| Contract | Purpose | Owner (module) | Input → output | Persistence | Lifecycle / events | Errors | Idempotency / concurrency | Recovery | Later owner |
|---|---|---|---|---|---|---|---|---|---|
| `create_project` (command, `admin` scope, D7) | register a project and its repositories | `core/application/world.py` | `{name, root_paths[], workspace_id?}` → `{project, repositories[]}` | `projects`, `repositories` | `project.created`, `repository.registered` (one per repo); repositories start `architecture_state=UNKNOWN` | 400 path not absolute / not a directory / no git repository under it; 409 `conflict` when a repo is already registered (detail: its project id) | key required; replay returns the stored result; repo uniqueness is a UNIQUE index on `(workspace_id, path_key)`, so two racing creates cannot both register a repo | none needed (one transaction) | P16 UI, P22 importer (creates the same rows from legacy projects) |
| `declare_constraint` (command, `control`) | declare a checkable architecture constraint for a project | `core/application/world.py` | `{project_id, kind, spec, statement}` → `{knowledge_item}` | `knowledge_items` (type ARCHITECTURE, origin explicit, `constraint={kind, spec}`) | `knowledge.created` + `knowledge.state_changed` (CANDIDATE → CONFIRMED, one transaction); the project's repositories go `constraints_changed` → STALE | 400 unknown kind, spec invalid for its kind, glob absolute or containing `..`; 404 project | key required; an identical `(project, kind, canonical spec)` already CONFIRMED returns the existing item with `changed:false` (a duplicate would double-report drift) | n/a | P6: retract, supersede, proposals, the three-way drift resolution |
| inspection commands `begin_inspection`, `complete_inspection`, `fail_inspection`, `record_assessment`, `sweep_inspections` (system principal only) | record one inspection of one repository at one revision | `core/application/world.py` | worker-computed `InspectionResult` + the constraint-set token it was evaluated against → inspection row + transitions | `repository_inspections`; payload as an **artifact** (content-addressed; the row keeps `payload_sha256`) | inspection machine SCHEDULED → RUNNING → COMPLETED \| FAILED; on completion the repository's architecture transition (§5); events in §4.3 | `VersionConflict` when the repository or its project's constraint set changed after evaluation (the worker re-evaluates: a lost race, as the engine treats one) | unique `(repository_id, revision, extractor_version)` among COMPLETED rows: a second completion for the same key is a no-op returning the first | boot sweep: RUNNING → FAILED (`core_restarted`) → SCHEDULED | P5/P6/P13 read the payload; P14 adds schedule triggers |
| `ack_digest` (command, `control`, D4) | advance the per-user "seen up to" cursor | `core/application/world.py` | `{up_to_seq}` → `{up_to_seq}` (the cursor after) | `users.last_ack_event_seq` | `user.digest_acked` (visibility **system**, so it never appears in a digest) | 400 `up_to_seq` negative or ahead of the head | monotone `max(current, up_to_seq)`, so a replay or a stale device cannot move it back; key **not** required — the operation is naturally idempotent | n/a | P15: the multi-device test; P16: the SPA dismissal (and the observe-scope question, §17) |
| `status(project_id?)` (query, `observe`) | S13 deterministic cross-project status | `core/application/queries.py` + `core/world/status.py` | → `{source:'deterministic', as_of_seq, projects[], missions[], drift[], unchecked[], inspections{…}, unknown_project[]}` (§8) | read only | none | 404 unknown `project_id` | one read transaction (a consistent snapshot) | n/a | P7 adds the brain summary beside it (S13's second function), never replacing it |
| `digest()` (query, `observe`) | S14: what happened after the cursor | `core/world/digest.py` | → `{from_seq, up_to_seq, count, groups[], truncated}` (§9) | read only | none | — | one read transaction | `truncated:true` when retention pruned events after the cursor | P16 renders; P7 may phrase the top line |
| `list_missions(project_id?)` | the project filter the judge already declares | queries | → missions of that project | read | — | 404 unknown project | — | — | — |
| `create_mission(project_id)` validation | a mission may name only a registered project | commands | as today | as today | as today | 404 `not_found` detail `{project_id}` | as today | — | — |
| `World` worker | cheap HEAD check, schedule, inspect, evaluate, submit | `core/world/worker.py`, started by `core/runtime.py` | registered repositories → inspection commands | none of its own (only through commands) | §6 | a failing repository becomes a FAILED inspection; an unexpected exception in the loop fails Core (exit 3), exactly as the engine does | one worker per Core (the Core lock already guarantees one Core per home); serial inspections | on boot, the sweep; see §12 | P14 adds event/schedule triggers and a file watcher |
| `/v1/health.world` | the judge's idle signal must see pending world work | `api/server.py` health | → `{state, pending}` where `pending` = repositories whose on-disk HEAD differs from their last inspected revision, plus SCHEDULED/RUNNING inspections | read | — | — | — | — | — |
| `CoreClient.create_project`, `.declare_constraint` (D1), and bodies for `.status`, `.digest`, `.ack`, the `list_missions` project filter | the judge contract | `tests/v1/judge/{client,http}.py` | as above | — | — | the §5.5 table | — | — | — |
| `Rig.fixture_repo(name)` | a real git repository built from `tests/v1/fixtures/repos/<name>/` | `tests/v1/judge/support.py` | → an object with `.path`, `.project_id`, `.repository_id`, `.commit(message, files)` | a temp dir | registers through `create_project` + `declare_constraint` (from the fixture's `constraints.json`), then **waits until the first inspection is COMPLETED**, so a scenario always starts from a baseline | — | — | — | — |

**Deliberately not established** (no entity is created because a feature exists): no
`DriftFinding` entity (findings are part of the inspection payload and its row's summary, so they
cannot disagree with the inspection they came from); no `ArchitectureConstraint` entity (it is a
KnowledgeItem, per context-and-knowledge §6); no Attention object (P9/P16); no Relation rows
(P6); no Project `health`/`status_line` maintenance (the one-sentence status line is a brain
output, P7).

`Harness ≠ Account ≠ Model ≠ Session ≠ Execution` is not touched: P4 introduces none of them.

---

## 4. Persistence

### 4.1 Migration `0003_world.sql`

Tables in the P2 shape (`id`, promoted columns, `version`, timestamps, audit pair, `body`):

| Table | Promoted columns | Constraints |
|---|---|---|
| `users` | — | at most one row per Core (the owner), written by the first digest acknowledgement |
| `projects` | `workspace_id`, `state` | — |
| `repositories` | `workspace_id`, `project_id` (FK projects), `path_key`, `architecture_state` | `UNIQUE (workspace_id, path_key)` |
| `repository_inspections` | `repository_id` (FK), `revision`, `extractor_version`, `state` | index `(repository_id, state)`; a partial-unique guarantee is enforced in the command (SQLite 3.31 has partial indexes, but a command check gives a typed error) |
| `knowledge_items` | `workspace_id`, `project_id`, `type`, `state` | index `(project_id, type, state)` |

Backup before migration is the existing P2 mechanism. `rows.TABLES` gains the five entities.

### 4.2 Entity field additions (additive; defaults keep every existing row valid)

- `User`: `last_ack_event_seq: int = 0`.
- `Project`: `root_paths` already exists; add `state` (ACTIVE/ARCHIVED, domain-model §4 default).
- `Repository`: `path_key` (normalised: `os.path.normcase(os.path.realpath(path))`),
  `last_inspection_id`, `last_revision`, `default_branch`, and the assessment: `findings`,
  `evaluated_against`, `evaluated_constraints`.
- `RepositoryInspection`: `extractor_version`, `inspected_at`, `dirty`, `complete` (false when
  the graph was truncated), `languages`, `dependencies`, `frameworks`, `docs`, `agent_config`,
  `test_commands`, `build_commands`, `payload_sha256` (the module graph and the dependencies);
  `diff_from_previous` (summary), `failure` and `failed_at` (on FAILED), `attempts` (counted
  failures). The findings, `evaluated_against` and `evaluated_constraints` are the Repository's
  (the assessment, above).
- `KnowledgeItem`: `constraint: dict = None` — `{kind, spec}` validated in `_check` when present;
  only ARCHITECTURE/DECISION items may carry one.

### 4.3 Event types added to `events.TYPES`

| Type | Subject | Visibility | In the digest as |
|---|---|---|---|
| `project.created` | project | user | "project added" |
| `repository.registered` | repository | system | — |
| `repository_inspection.state_changed` | repository_inspection | system | — |
| `architecture.state_changed` | repository | user | "drift found" when `to = DRIFTED`, "drift cleared" when DRIFTED → CONSISTENT; STALE edges are system-noise and are **not** emitted as user-visible (the payload carries `from`, `to`, `trigger`) |
| `knowledge_item.created`, `knowledge_item.state_changed` | knowledge_item | user | "constraint declared" |
| `user.digest_acked` | user | system | — |

`project.changed`, `repository.file_added`, `repository.model_added` (already registered in P1)
are **not** emitted by P4: a HEAD move is recorded as the architecture transition and the
inspection, and emitting a second event for the same fact would give the digest two bullets for
one thing. They stay registered for P14's triggers.

---

## 5. State machines

`repository_inspection` is used as P1 wrote it. `architecture` (`Repository.architecture_state`)
gains four edges (D5):

| Edge | Trigger | Why it must exist |
|---|---|---|
| `UNKNOWN → DRIFTED` | `first_inspection_drift` | a repository registered after its constraint and already violating it |
| `DRIFTED → STALE` | `revision_moved` | a fix commit; without it DRIFTED is left only by the P6 resolution, and a repaired repository reports drift forever |
| `CONSISTENT → STALE` | `constraints_changed` | a constraint declared on an inspected repository must be evaluated, and the result must not be reported as current until it is |
| `DRIFTED → STALE` | `constraints_changed` | the same, from a drifted repository |

Reinspection and re-evaluation leave STALE through the existing `reinspected_no_drift` /
`reinspected_drift`. The three resolution edges out of DRIFTED (`architecture_updated`,
`drift_accepted_as_change`, `drift_rejected_mission_created`) stay in the table and are **not
fired in P4** (P6). state-machines.md §10's diagram and prose change in the same commit; the
P3 guard pattern applies: `reinspected_*` require an inspection COMPLETED at the repository's
current revision, `first_inspection*` require no prior completed inspection.

---

## 6. The world worker and the inspection pipeline (P4's execution architecture)

P4's "execution" is Core's own deterministic work, not a harness execution. There is no Task,
no Execution row, no adapter and no process registry: inspecting a repository is not a mission
task (TASK_KINDS' `inspection` is a *mission* task kind for research work and is not used here).

### 6.1 Loop

One thread, `archeus-world`, started after the engine and stopped before it (the P3.5b start
order grows by one step: … engine → **world** → HTTP → `core.json`). The in-process judge binding
has no threads and pumps one world pass from `_idle()`, exactly as it pumps the engine.

Each pass (default every 10 s, injectable; also woken by the writer's commit notification):

1. Read the registered repositories and their last inspection (one read transaction).
2. **Cheap check** per repository: resolve HEAD to a SHA from the filesystem (§6.2). Due when
   the SHA differs from `last_revision`, when the project's constraint-set token differs from the
   last inspection's `evaluated_against`, when no inspection exists, or when the last one FAILED
   and its retry is due. Otherwise nothing is written and nothing is emitted.
3. For each due repository, serially: `begin_inspection` (SCHEDULED → RUNNING, and the
   `revision_moved` edge when the revision moved), then either
   - **re-evaluate only** when the revision is unchanged and only the constraints moved: load the
     previous payload from the artifact store, evaluate, `complete_inspection`; or
   - **inspect**: run the deterministic pass (§6.3) outside any transaction, **re-read HEAD**; if
     it moved during the walk, discard the result and fail the attempt as `revision_moved_during`
     (retried at once at the new HEAD); otherwise write the payload artifact, evaluate the
     constraints read in step 1, and `complete_inspection` with that constraint-set token.
4. `complete_inspection` re-reads the project's CONFIRMED constraints inside the transaction and
   refuses with `VersionConflict` if their token differs from the one evaluated against (a
   constraint was declared meanwhile); the worker re-evaluates on its next pass. The drift outcome
   therefore always matches the constraints current at commit.

Stop: the stop flag is checked between repositories. A walk in progress cannot be interrupted
(it is in-process Python); Core's stop waits for it up to the existing drain timeout and then
abandons it (the thread is a daemon), leaving a RUNNING row that the next boot sweeps.
`ponytail:` one serial in-process worker; a very large repository delays the others and stop
waits on its walk. Upgrade path: run the pass in a subprocess (`proc.kill_tree` makes it
cancellable) when a real repository shows it matters.

### 6.2 HEAD resolution (no subprocess on the hot path)

`.git` is a directory or a `gitdir:` file (submodule, linked worktree — the `repos.classify`
rule). Read `HEAD`; a detached SHA is the answer; `ref: refs/heads/x` resolves through the
gitdir, then the `commondir` (a linked worktree keeps its refs in the main repository), then
`packed-refs`. Anything else (unusual ref storage, a corrupted file) falls back to `git rev-parse
HEAD` in the repository through the existing `repos._git` (UTF-8 pinned). `repos.head_branch`
is **not** enough: it returns the branch name, not the revision.

### 6.3 Deterministic pass

A pure function `inspect(path) -> InspectionResult` in `core/world/inspection.py`:

- languages (extension breakdown — `connections` meta already computes it), manifests →
  dependencies and frameworks (`pyproject.toml`, `requirements*.txt`, `package.json`, `*.csproj`,
  `Cargo.toml`, `go.mod`), docs (`README*`, `docs/`), agent config (`CLAUDE.md`, `AGENTS.md`,
  `.claude/`), test/build commands (manifest scripts; the marker-file fallback execution-
  architecture already specifies for CodeVerifier), the module graph from
  `connections.build_hierarchy(path, force=True)`, and `dirty` from the working tree.
- `diff_from_previous`: modules added/removed, dependency and framework changes, changed commands,
  changed agent config.
- `extractor_version`: a constant bumped whenever any extractor's output can change, so a stored
  inspection is never reused across an extractor fix: the next assessment that needs an
  observation walks again (see the as-built note on upgrades).

Four properties of `build_hierarchy` the design works around rather than changes (it is REUSE
AS-IS, and splitting it is explicitly not done — migration-plan §3):

1. **Its cache key is `(file count, whole-second max mtime)`**, so an edit in the same second
   can return a stale graph. P4 always passes `force=True`; the cheap HEAD check is what makes
   that affordable.
2. **It truncates** at 12,000 files and 8,000 dependency edges and says so in `meta.truncated`.
   A truncated graph sets `complete=false`, and every edge-based constraint is reported as
   `unchecked: graph_truncated` — never as satisfied.
3. **It writes `connections-cache.json`** under the inspected repository's `.archeus/` (the
   shared cache of migration-plan §5, seeded with a `*` `.gitignore`, so HEAD is unaffected).
   D8 accepts that as the documented legacy behaviour; the alternative is a legacy edit.
4. **It includes nested repositories** (submodules) in the walk. A Repository's inspection keeps
   only nodes and edges whose cluster is that repository; a submodule is its own Repository row.

Working tree, not the commit: the pass reads files on disk. An inspection records `dirty`, and a
finding from a dirty tree is marked `provisional` in `status()`. Re-inspection is triggered by
HEAD, not by uncommitted edits (the file watcher / `PROJECT_CHANGED` trigger is P14's).

### 6.4 Drift evaluation

A pure function `evaluate(result, constraints) -> findings` in `core/world/drift.py`. Globs are
relative to the repository root (`fnmatch` over `/`-separated paths; `**` spans directories).

| Kind | Spec | Violation | In P4 |
|---|---|---|---|
| `forbid_dependency` | `{from, to}` | any file edge `src ∈ from`, `dst ∈ to` | checked |
| `require_layering` | `{layers: [glob, …]}` top to bottom | an edge from a lower layer to a higher one (expands to `forbid_dependency` pairs) | checked |
| `module_exists` | `{path}` | no file matches | checked |
| `framework_pinned` | `{package, version?}` | the dependency is absent, or its declared specifier does not satisfy `version` (string prefix/equality only — no resolver) | checked |
| `doc_matches_code` | `{doc, code}` | — | **unchecked** (`cannot check automatically`): it needs either a model or a definition this repository does not have |
| no kind (prose) | — | — | **unchecked** |

A finding: `{constraint_id, constraint (the statement), kind, status: violated|satisfied|
unchecked, reason?, violations: [{from, to}] (first 20) , violation_count, provisional}`.

---

## 7. Resource selection, context, verification and review boundaries

- **Resource selection:** none (§2).
- **Context (P5):** P4 builds no context package and no L0–L4 assembly. It produces the
  inspection record P5's L1 (project) level reads, and it is the only P4 output P5 depends on.
  The minimum context capability "for the first useful reasoning slice" is P5's to define,
  against G2.
- **Verification / review (P13):** P4 verifies nothing a mission did. The inspection's
  `test_commands`/`build_commands` are the input execution-architecture's CodeVerifier reads
  later. Drift is not a verification: it judges a repository against its declared architecture,
  not a mission's result against its criteria. No P9 authorization moves into either.

---

## 8. `status()` (S13, deterministic)

One read transaction; nothing computed that the rows do not already say.

```
{ source: 'deterministic', as_of_seq,
  projects: [{id, name, state, repositories: [{id, path, kind, architecture_state,
              last_revision, last_inspection: {id, state, inspected_at, complete, dirty}}],
              missions: {<state>: count}}],
  missions: [<mission view>],             # not settled first, then by updated_at
  drift:    [<finding with status violated> + {repository_id, project_id, revision}],
  unchecked:[<finding with status unchecked> + …],
  unknown_project: [<mission id>] }      # pre-P4 rows whose project_id names nothing (C7)
```

`project_id` narrows every list to one project. `drift` lists the findings of each repository's
**latest COMPLETED inspection at its current revision**; a STALE repository's old findings are
listed with `stale: true`, so "no drift" is never claimed for a revision nobody has checked.

## 9. `digest()` and `ack` (S14, one device)

- Events with `seq > users.last_ack_event_seq` and `visibility = user`, grouped by subject
  (mission, project, repository), each group `{ref, headline_kind, count, first_seq, last_seq}`,
  with headline kinds derived deterministically: `completed`, `failed`, `needs_you` (a mission in
  APPROVAL_REQUIRED, REVIEW or BLOCKED at the head), `drift_found`, `drift_cleared`,
  `progressed` (anything else). Ordered `needs_you`, `drift_found`, `failed`, `completed`,
  `progressed`, then by `last_seq` descending. `count` is the number of groups.
- `up_to_seq` is the head seq **of the read**, so `ack(up_to_seq)` acknowledges exactly what was
  shown, never an event committed after it.
- If retention pruned events after the cursor, `truncated: true` and `from_seq` is the oldest
  retained seq (outbox semantics; no `CursorExpired` error — the digest is a summary, not a
  replay).
- A brain-phrased top line is P7's; every group already links its object, which is the S13/S14
  "every claim links" rule applied in advance.

## 10. Routes, scopes and the CoreClient

Added to the P3.5b table (the pin test grows to "§5.1 of the P3.5b gate plus this table,
exactly"):

| Method | Path | Scope | Idempotency | Schema (req → resp) |
|---|---|---|---|---|
| GET | `/v1/status` | observe | — | `?project=` → `Status` |
| GET | `/v1/projects` | observe | — | → `ProjectList` |
| GET | `/v1/projects/{id}` | observe | — | → `Project` (with repositories) |
| POST | `/v1/projects` | **admin** (D7) | required | `CreateProject` → `ProjectCreated` |
| POST | `/v1/projects/{id}/constraints` | control | required | `DeclareConstraint` → `KnowledgeItem` |
| GET | `/v1/repositories/{id}/inspections` | observe | — | `?limit=` → `InspectionList` (rows, not payloads) |
| GET | `/v1/digest` | observe | — | → `Digest` |
| POST | `/v1/digest/ack` | control | not required (monotone) | `{up_to_seq}` → `{up_to_seq}` |

`GET /v1/missions` gains `?project=`. Not added: `/v1/repositories/{id}/inspect` (the worker
covers it; a manual trigger arrives with the UI that needs it), `/v1/world/graph` (P18),
`/v1/now` (P16), `/v1/attention` (P9/P16), `/v1/knowledge*` beyond the constraint write (P6).
The generated `api-reference.md` and `generated.ts` are regenerated; the SPA does not use the
new routes in P4.

`CoreClient` (D1): `create_project(*, name, root_paths, idempotency_key=None) -> dict` and
`declare_constraint(*, project_id, kind, spec, statement, idempotency_key=None) -> dict` are
added; `status`, `digest`, `ack` and the `list_missions` filter get bodies on both bindings.
`IMPLEMENTED` grows by those six names.

---

## 11. Failure and recovery

| Failure | Persisted | Event | Retry | User-visible | Terminal? |
|---|---|---|---|---|---|
| root path missing / not a directory / no repo under it | nothing | none | — | 400 | the request |
| repository already registered | nothing | none | — | 409 with the owning project | the request |
| repository directory deleted or unreadable | inspection FAILED `repository_missing` / `unreadable` | inspection state (system) | yes, backoff 1 min → 1 h, **3 attempts per revision**, then it waits for HEAD to move | `status()` shows the failure on the repository; architecture state unchanged | per revision |
| HEAD unresolvable, `git` fallback fails | inspection FAILED `head_unresolvable` | same | same | same | per revision |
| manifest or source file that will not parse | not a failure: that extractor records a `findings[]` note and the pass completes | — | — | a note in the inspection | no |
| graph truncated | inspection COMPLETED, `complete=false` | as usual | — | edge constraints listed as unchecked | no |
| HEAD moved during the walk | attempt FAILED `revision_moved_during` | system | at once, at the new HEAD, not counted against the cap | nothing (transient) | no |
| constraint declared between evaluation and commit | nothing (the command refuses) | none | the next pass re-evaluates | nothing | no |
| Core killed mid-inspection | RUNNING row left | — | boot sweep: RUNNING → FAILED `core_restarted` → SCHEDULED; not counted against the cap | nothing | no |
| unexpected exception in the worker loop itself | whatever committed | Core log | none — Core exits 3, like the engine | `archeus status` reports it | Core |
| digest cursor older than retention | nothing | — | — | `truncated: true` | no |
| `ack` ahead of the head | nothing | — | — | 400 | the request |

Model unavailable, account unavailable, model timeout, malformed or invalid structured output,
execution/verification/review failure, retry exhaustion of executions, superseded plans,
duplicate dispatch and resource exhaustion have no P4 path: they belong to P7 (structured
output: retry once, then ask), P10 (resource), P11 (execution), P13 (verification/review) and
the P3 guards already in place (superseded-plan dispatch, duplicate dispatch).

## 12. Idempotency and concurrency invariants

1. Every P4 command runs in one writer transaction; the only concurrency control is P2's
   (`VersionConflict` on `expected_version`, idempotency keys) and P3's (machine + proof). No
   parallel mechanism is introduced.
2. A repository is registered at most once per workspace (`UNIQUE (workspace_id, path_key)`,
   `path_key` case-folded and real-path-resolved, so `D:\X`, `d:/x` and a junction to it are one
   key).
3. At most one COMPLETED inspection per `(repository_id, revision, extractor_version)`; a
   duplicate completion (restart, reconnect) returns the first and writes nothing.
4. A drift outcome is committed only against the constraint set it was evaluated with (§6.1
   step 4).
5. An inspection result is committed only if HEAD did not move during its walk (§6.1 step 3).
6. The digest cursor never moves backwards (`max`), and acknowledges only what a read showed.
7. Exactly one world worker per home: the Core lock (P3.5b) already guarantees one Core, and the
   in-process binding takes the same lock (P3.5b A1).
8. Missions are unaffected: P4 adds no mission, plan, task or execution transition.

---

## 13. Acceptance scenarios

### 13.1 Judge functions P4 turns green (strict xfail removed; both bindings)

| Id | Function | Given / When / Then |
|---|---|---|
| J1 | `test_s07_drift::test_a_commit_that_violates_a_constraint_is_reported_as_drift` | fixture `layered-python` registered with "core must not import api" and inspected / commit `app/core/x.py: import app.api` / `status()['drift']` names that constraint |
| J2 | `test_s07_drift::test_a_clean_commit_is_not_drift` | same baseline / a clean commit / `status()['drift'] == []` |
| J3 | `test_s13_status::test_status_is_answered_without_the_brain` | a mission / `status()` / missions listed, `source == 'deterministic'` |
| J4 | `test_s14_digest::test_the_digest_lists_what_happened_since_the_last_ack` | ack to the head / a mission is created / `count >= 1` and `up_to_seq` moved |

J2 as written passes as soon as the baseline is clean, without waiting for the new commit's
inspection — a weak gate (adversarial A9). W06 is the strong form, and P4 adds it rather than
rewriting a frozen judge function.

### 13.2 P4's own scenarios (`tests/v1/integration/test_world_*.py`, fixture repos under `tests/v1/fixtures/repos/`)

Fake/real: every scenario uses **real** git repositories built in a temp dir and the real
deterministic pass; no model; missions (where present) run the P3.5 stub ports and fake harness.

| Id | Given | When | Then (persisted · events · visible) |
|---|---|---|---|
| W01 | fixture tree: a repo, a submodule, a linked worktree | `create_project(root)` | three Repository rows with kinds repo/submodule/worktree, the worktree not counted twice · `project.created`, 3 × `repository.registered` · 200 with the rows |
| W02 | W01 done | the same key again; a second project over the same repo | replay → identical body; second project → 409 naming the first · nothing new |
| W03 | — | root not absolute / missing / no repo | 400 per case · nothing written |
| W04 | Python and TS fixtures registered | worker pass | inspection COMPLETED at HEAD with languages, dependencies, commands, modules; UNKNOWN → CONSISTENT · state events · `status()` shows the inspection |
| W05 | W04 done | three more passes, HEAD unchanged | zero new rows, zero new events (the cheap check) |
| W06 | W04 done | clean commit, **wait for the new revision's inspection** | STALE → CONSISTENT at the new revision; drift `[]` (the strong J2) |
| W07 | `forbid_dependency` | violating / clean commit | DRIFTED + finding / CONSISTENT (J1/J2 in integration form) |
| W08 | `require_layering` | edge upward / downward | violated / satisfied |
| W09 | `module_exists` | path removed / present | violated / satisfied |
| W10 | `framework_pinned` | dependency absent or mis-pinned / pinned | violated / satisfied |
| W11 | `doc_matches_code`; a prose-only ARCHITECTURE item | inspection | listed under `unchecked` with a reason, repository not DRIFTED because of them |
| W12 | an inspected CONSISTENT repo | `declare_constraint` it violates | `constraints_changed` → STALE → DRIFTED **without a new walk** (same revision; no second payload artifact) |
| W13 | constraint declared before the repo's first inspection | first pass | UNKNOWN → DRIFTED (`first_inspection_drift`) |
| W14 | a DRIFTED repo | commit that removes the violation | DRIFTED → STALE → CONSISTENT · `architecture.state_changed` "drift cleared" in the digest |
| W15 | a fixture beyond the edge cap (cap lowered by monkeypatch) | inspection | `complete=false`, edge constraints unchecked, never satisfied |
| W16 | a walk paused by a monkeypatched extractor | commit during the walk | attempt FAILED `revision_moved_during`, then COMPLETED at the new HEAD |
| W17 | a registered repo | directory deleted | FAILED `repository_missing`, retries capped at 3, other repos still inspected |
| W18 | an inspection RUNNING (walk blocked) | Core killed (`TempCore` process mode) and restarted | sweep → FAILED `core_restarted` → SCHEDULED → COMPLETED; exactly one COMPLETED row for that revision |
| W19 | a COMPLETED inspection | `complete_inspection` submitted again for the same key | no-op, same row returned, no event |
| W20 | an evaluation in flight | `declare_constraint` lands before the completion commits | completion refused (`VersionConflict`), next pass re-evaluates; outcome reflects the new constraint |
| W21 | projects with missions and drift | `status()`, `status(project_id)`, unknown id | J3 plus filtering; 404 for unknown; a pre-P4 mission with a dangling `project_id` listed under `unknown_project` |
| W22 | — | `list_missions(project_id)`; `create_mission(project_id=unknown)` | filtered list; 404 |
| W23 | events after the cursor | `digest()`, `ack(up_to_seq)` twice, `ack(head+1)`, `ack(-1)` | groups by subject with headline kinds; second ack a no-op; 400 twice; J4 |
| W24 | retention pruned past the cursor | `digest()` | `truncated: true`, `from_seq` = oldest retained |
| W25 | system-visibility events only after the cursor | `digest()` | `count == 0`; `user.digest_acked` never counted |
| W26 | a registered repo, engine idle | commit, then immediately `support.idle()` on the HTTP binding | **False** (`health.world.pending` sees the new HEAD) — without this J1 would fail fast as "not built yet" |
| W27 | the route table | pin test | P3.5b §5.1 ∪ §10 exactly; no P9/P10/P11/P15/P16 route; no `archeus/core/world` module imports a model runner, the brain, `rotate` or `quota` |
| W28 | an observe-only device (launch code) | create project / declare / ack; status / digest | 403 `scope_required` ×3; 200 ×2 |
| W29 | — | constraint spec with an absolute path or `..`; root path that is a file | 400 each |
| W30 | an SSE stream open | a drift is found | the stream carries `architecture.state_changed` ids only (ADR-0009), after the commit |

### 13.3 The brief's scenarios A–T, placed

| Brief | Owner | P4 coverage |
|---|---|---|
| A intent → mission | P7 | none (create_mission exists) |
| B minimum context | P5 | W04 produces the L1 input |
| C–D plan produced, versioned | P7, P8 | none |
| E task executable, O superseded task, P duplicate dispatch | P3 guards (in place), P8 | none (untouched; P3 tests stay green) |
| F resource selected | P10 (P7 shim) | none |
| G controlled model execution, T real-model boundary | P7 (first real call, after ADR-0021) | W27 asserts P4 makes none |
| H result persisted, M failed execution | P11 | none |
| I verification, J review, K accepted completes, L rejection keeps it open | P13 (stubs + P3 guards today) | none |
| N replanning | P8 (S6) | none |
| Q restart keeps state | P3.5b for missions | W18 for world state |
| R model/resource failure recoverable | P7/P10 | W17 for repository failure |
| S fake path exercises the slice | P3.5 (walking skeleton) | unchanged |

---

## 14. Adversarial review

| # | Attack | Result | Resolution |
|---|---|---|---|
| A1 | The judge's idle signal reports idle between a commit and the worker noticing it, so `wait_for` raises "not built yet" and J1 fails on the HTTP binding | **real, would block S7** | `health.world.pending` computed from a fresh cheap HEAD check (§3.2); `HttpClient._idle` and the in-process pump both include it (W26) |
| A2 | Drift evaluated against constraints that changed before commit | real | constraint-set token checked in the completing transaction (§6.1.4, W20) |
| A3 | HEAD moves while the walk reads files: the result mixes revisions | real | HEAD re-read after the walk; mismatch discards (W16) |
| A4 | `build_hierarchy` returns a stale cached graph for a same-second edit | real | `force=True` always (§6.3.1) |
| A5 | A truncated graph reports "no drift" | real | `complete=false`, edge constraints unchecked (W15) |
| A6 | A first inspection that already violates, or a fix commit, cannot be represented | real (machine gap) | D5 edges (W13, W14) |
| A7 | Worktree HEAD read from the worktree's gitdir finds no loose ref (refs live in the common dir) | real | `commondir` + `packed-refs` resolution, `git rev-parse` fallback (W01 fixtures) |
| A8 | Same repository registered twice through different spellings of its path (case, slashes, junction) | real on Windows | `path_key` = normcase(realpath) with a UNIQUE index (W02) |
| A9 | J2 passes vacuously (it does not wait for the new inspection) | real (weak gate) | W06; the rig waits for the baseline so J2 at least cannot pass on an uninspected repo |
| A10 | Declaring the same constraint twice doubles every finding | real | canonical duplicate returns the existing item (§3.2) |
| A11 | A submodule's files counted inside its parent's constraint scope | real | cluster filter (§6.3.4) |
| A12 | A dirty working tree reported as the committed revision's architecture | real | `dirty` + `provisional` (§6.3); dirty-only changes do not retrigger (P14 owns the file watcher) |
| A13 | Retry storm on a permanently broken repository | real | 3 attempts per revision with backoff (§11) |
| A14 | Core killed mid-inspection leaves RUNNING forever or a duplicate COMPLETED | real | boot sweep + completion uniqueness (W18, W19) |
| A15 | A device acks on stale state and moves the cursor back, or acks events it never saw | real | `max` + `up_to_seq` is the head of the read (§9, W23) |
| A16 | The digest counts its own ack | real | `user.digest_acked` is system-visible (W25) |
| A17 | Root path points at a whole drive: the walk and the reads go everywhere | accepted ceiling | `admin` scope (D7), depth-4 discovery, `build_hierarchy`'s file caps; reported in the project row. Remote devices cannot reach it until P15 pairing, which must revisit the scope |
| A18 | Status exposes file paths and import edges of any registered repo to every observe device | accepted | single user, local; P15 revisits per-device visibility (already deferred there by P3.5b) |
| A19 | A constraint glob escapes the repository (`../`, absolute) | real | rejected at declaration (W29) |
| A20 | Inspection writes into the user's repository (`.archeus/connections-cache.json`) | accepted (D8) | documented legacy behaviour, git-ignored by its seeded `.gitignore`; HEAD unaffected; W04 asserts `git status --porcelain` stays clean |
| A21 | A worker bug crash-loops Core | accepted, like the engine | exit 3; `archeus status` reports it; a repository's own failure never reaches the loop (per-repo try) |
| A22 | Two missions modify the same project | not P4 | P8 (`touches` serialisation), P11 (worktrees) |
| A23 | User pauses or changes intent while reasoning | not P4 | P3 pause (in place), P7 |
| A24 | Provider terms unavailable | not P4 | §2: no P4 path depends on it |
| A25 | Fake and real harness diverge | not P4 | P11 contract tests on recorded streams |
| A26 | The model claims a task complete / produces an invalid plan | not P4 | P3 guards (in place), P7 schema validation, P8 DAG validation, P13 |
| A27 | Context contains stale information | partly P4 | P4 marks STALE and provisional; P5 down-ranks and labels |

No unresolved blocker: every "real" row has a resolution inside this design; every "not P4"
row names its owner.

---

## 15. Traceability

| Requirement (source) | Decision | Contract | Scenario | Location | Later dependency |
|---|---|---|---|---|---|
| repositories registered per project, kinds repo/submodule/worktree (domain-model §4, migration-plan §2) | D1, D7 | `create_project` | W01–W03, W29 | `application/world.py`, `world/projects.py` | P22 importer, P16 UI |
| cheap change check from `.git/HEAD` (context-and-knowledge §6.2, state-machines §10) | — | worker §6.1–6.2 | W05, W26, A7 | `world/worker.py`, `world/inspection.py` | P14 triggers |
| deterministic pass sufficient, model pass disabled (plan P4, §31.4) | D2 | `inspect()` | W04, W27 | `world/inspection.py` | P6 model pass |
| diff vs previous (context-and-knowledge §6.5) | — | `diff_from_previous` | W06 | `world/inspection.py` | P5 |
| drift against checkable constraints, prose uncheckable (§6.6, testing-strategy §3) | D3 | `declare_constraint`, `evaluate()` | W07–W13, J1, J2 | `world/drift.py` | P6 resolution |
| architecture machine (state-machines §10) | D5 | §5 edges | W12–W14 | `domain/states.py`, `guards.py` | P6 resolution edges |
| S13 deterministic status (testing-strategy §2) | — | `status()` | J3, W21 | `world/status.py`, `queries.py`, `/v1/status` | P7 brain summary |
| S14 per-user cursor (domain-model §3.1, context-and-knowledge §9) | D4 | `digest()`, `ack_digest` | J4, W23–W25 | `world/digest.py`, `/v1/digest*` | P15 multi-device, P16 `/v1/now` |
| project scoping of missions (judge "arrives with projects (P4)") | C7 | `list_missions` filter, `create_mission` validation | W21, W22 | `queries.py`, `commands.py` | — |
| restart safety (P3.5b boot sweep pattern) | — | sweep over inspections | W18, W19 | `runtime.py`, `world/worker.py` | P11 (processes) |
| idempotency / concurrency (P2) | — | §12 | W02, W19, W20, W23 | `application/world.py` | — |
| ids-only realtime (ADR-0009) | — | §4.3 event types | W30 | `domain/events.py` | P16 |
| route table single source + scopes (P3.5b §4–§5) | D7 | §10 | W27, W28 | `api/routes.py`, `schemas.py` | P9 finer scopes |
| no real model call before ADR-0021 (ADR-0021, §31.4) | D2 | structural guard | W27 | `tests/v1/unit/test_world_structure.py` | P6/P7 gate |

Every P4 requirement has a scenario; every W/J scenario traces to a requirement row. The P4
judge rows keep their phase ranges (S7 P4; S13 P4, P7; S14 P4, P15), so `test_traceability.py`
needs no change beyond the four functions losing their xfail marks.

---

## 16. Phase boundaries

| | |
|---|---|
| **P4 owns** | projects and repositories (registration, discovery), repository inspection (deterministic), the cheap HEAD check and the world worker, architecture constraints (declaration only) and drift detection, the `architecture` machine amendments, deterministic cross-project status, the since-you-left digest and the per-user cursor for one device, project scoping of missions |
| **P4 consumes** | §3.1 |
| **P4 establishes** | §3.2 and the persisted inspection record for P5/P6/P13 |
| **defers to P5** | context packages and L0–L4 assembly; ranking stale items |
| **defers to P6** | the inspection model pass; knowledge beyond the constraint write (retract, supersede, proposals, relations, learning); the three-way drift resolution |
| **defers to P7** | the brain summary of S13, phrasing the digest's top line, the project status line, intent, the first real model call (after ADR-0021) and the pre-router account shim |
| **defers to P9** | authorization of any world action beyond coarse scopes; policy class `spend` for the model pass; Attention as approvals |
| **defers to P10** | any account or model selection |
| **defers to P11** | process registry, adoption, tailing, pause/stop/e-stop, worktree management; running inspection in a cancellable subprocess if it ever matters |
| **defers to P14** | `PROJECT_CHANGED` from a file watcher/post-commit hook, schedule-triggered re-inspection, after-merge re-inspection |
| **defers to P15** | acknowledging on one device and clearing on the others (S14 second function); per-device visibility; the scope of `create_project` for remote devices |
| **defers to P16** | `/v1/now`, Attention drift proposals in the UI, World views, SPA use of the new routes, whether an observe device may ack |
| **defers to P18** | `/v1/world/graph` |
| **defers to P22** | importing legacy projects and repositories into these tables |

No later-phase prerequisite is hidden: the only thing P4 needs from a later phase's territory is
the constraint write path (P6's table), and D3 moves exactly that, with the rest left in P6.

---

## 17. Implementation sequence

Each slice ends green (full suite + `tests/v1`), and each new gate is watched failing by mutation
before it is trusted (the P3.5b method; a first commit of strict xfails is not required).

| # | Slice | Proves |
|---|---|---|
| 0 | **Decision pass** on D1–D8 (§19) | — |
| 1 | **Contracts:** entity fields, the four machine edges + state-machines.md, event types, `0003_world.sql` + `rows.TABLES`, owner-user bootstrap; `CoreClient` additions + testing-strategy §1.1 + `test_core_client.py` DOCUMENTED; route rows + schemas + pin test; generated docs/client | unit: domain, machines (`test_state_tables.py`), migration, codec; contract parity |
| 2 | **Spike, then the pass:** confirm `connections` resolves `import app.api` to `app/api/__init__.py` in the `layered-python` fixture (the one assumption J1 rests on); then `world/inspection.py` (HEAD resolver, extractors, `InspectionResult`) over the Python, TS, submodule and worktree fixtures | unit: W01 kinds, A7, W04 fields |
| 3 | **Drift:** `world/drift.py`, four kinds + unchecked | unit: W08–W11 positive/negative per kind, W15 |
| 4 | **Commands:** `create_project`, `declare_constraint`, `start/complete/fail_inspection`, guards, idempotency | integration: W02, W03, W19, W20, W29 |
| 5 | **Worker:** `world/worker.py`, runtime start/stop order, boot sweep, `health.world`, both `_idle` paths; `Rig.fixture_repo` | W05, W06, W12–W14, W16–W18, W26; **J1, J2** on both bindings |
| 6 | **Status:** `world/status.py`, `/v1/status`, `/v1/projects*`, mission filter and validation | W21, W22, **J3** |
| 7 | **Digest:** `world/digest.py`, `/v1/digest`, `/v1/digest/ack` | W23–W25, **J4**, W30 |
| 8 | **Close:** W27/W28 structural and scope tests, backend mutation pass extended to the world gates, plan §31.1 P4 "as built", api-and-realtime §2 (C3), ADR-0021 text (C6), full validation (the P3.5b closure list) | the gate |

Smallest first vertical slice: slices 1–2–4–5 for `forbid_dependency` only — register a fixture
repo, inspect it, commit a violation, see J1 green on the in-process binding. Everything after
widens that slice rather than adding a second one.

## 18. Documents that change during implementation (not now)

state-machines.md §10 (D5) · testing-strategy §1.1 operation list (D1) · api-and-realtime §2
Presence and World rows (C3, D4) · domain-model §4/§5 (inspection fields, the constraint field)
· ADR-0021 decision text (C6) · plan §31.1 P4 "as built" · `api-reference.md` (generated).

## 19. Decision pass

| # | Decision | Recommendation | If rejected |
|---|---|---|---|
| D1 | Add `create_project` and `declare_constraint` to the frozen `CoreClient` | accept — S7 cannot be written under the judge's own "contract-level only" rule without them | S7 cannot pass in P4 → **NOT_READY** |
| D2 | No inspection model pass in P4; it moves to P6; P4 makes zero real model calls | accept — the plan makes it optional and the deterministic pass must suffice | P4 gains the `llmcall` path and ADR-0021 becomes a P4 prerequisite for that path |
| D3 | Pull the ARCHITECTURE-constraint write (table + declare, auto-confirmed as explicit) forward from P6 | accept — drift has nothing to check against otherwise | constraints would need a second, non-knowledge store that P6 then migrates |
| D4 | `/v1/digest` + `/v1/digest/ack` in P4; `/v1/now` (P16) embeds it; ack needs `control` in P4 | accept | implement a partial `/v1/now` in P4, which the P3.5b gate assigns to P16 |
| D5 | Four `architecture` machine edges (§5) | accept | fixes and constraint changes cannot be represented; W12–W14 impossible |
| D6 | Inspect the working tree at HEAD, with `dirty`/`provisional`; re-inspect on HEAD moves only; 10 s default poll | accept | reading the committed tree (`git archive`/`ls-tree` + `show`) costs a subprocess per file set and is not what `connections` does |
| D7 | `create_project` requires `admin` (it gives Core filesystem reach) | accept | `control` — any control device could point Core at any directory |
| D8 | Accept `connections.build_hierarchy`'s write of `.archeus/connections-cache.json` into inspected repositories | accept — documented legacy behaviour, ignored by git | a legacy edit adding a no-cache flag (a seam in migration-plan §3) |

**Readiness.** Scope coherent (§1); acceptance executable (§13, with the one assumption J1 rests
on spiked first, slice 2); fake/real explicit (§2, §13.2); ADR-0021 placed (§2); no hidden
P9/P10/P11/P15/P16 dependency (§16); persistence (§4), lifecycle (§5), restart (§11, W18),
concurrency and idempotency (§12), resource-selection seam (none needed, §2), context seam (§7),
verification/review seam (§7), failure and retry (§11) defined; traceability complete (§15);
no unresolved adversarial blocker (§14); sequence concrete (§17).

**DESIGN_GATE = READY_FOR_IMPLEMENTATION**, conditional on D1 (without it S7 is unwritable) and
on the decision pass accepting or amending D2–D8.
