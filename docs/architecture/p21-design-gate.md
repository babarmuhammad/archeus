# P21 design gate — observability views

**APPROVED 2026-10-19 (decisions D0-D14, §4.1). P21 cannot be declared complete before P20 is.**

Status: **DRAFT** (Claude, card T-117, 2026-10-19). Written at the owner's request ("Draft it now
(Recommended)") while P20 is still open: slice G is paused (p20-design-gate §12 items 92–101) and
slice K has not run. D0 is DECIDED by the owner (2026-10-19, below): named slices that touch no
isolation, boundary, credential or auth code may be built before P20 completes. Every other decision
in §4 is open, and no slice is authorised until its own decisions are approved.

Sources read, in precedence order: the plan
([ARCHEUS_V1_REARCHITECTURE_PLAN.md](ARCHEUS_V1_REARCHITECTURE_PLAN.md) §28 and §31.1 P21), ADR-0030
§4, ADR-0031 §6, ADR-0043, ADR-0047 (with its "As built"), ADR-0048 D-25.4,
[p20-design-gate.md](p20-design-gate.md) D8, D11 and §14.C, [p14-design-gate.md](p14-design-gate.md)
D14, [r13-design-review.md](r13-design-review.md) §5,
[testing-strategy.md](testing-strategy.md) §10 and the orchestration gates table (G6, G8, G12,
G13), and this repository at `4d37280`.

---

## 0. What P21 is, and what it is not

P21 makes the system's record readable: plan §31.1 P21 names a trace view per mission,
`metrics_daily`, a Health page and `archeus doctor`, plus the observability foundations ADR-0031,
ADR-0043 and ADR-0047 assign to it. Its acceptance is the plan's: **every question in §28 is
answerable from the UI**. It adds views and records over mechanisms that exist since P2 (events,
decisions); it changes no routing behaviour (plan §31.1 P21; ADR-0047 clause 12). It does not
build the Codex adapter (P23, p20 D9), the Resources UI or project defaults (P22), or anything in
PV-20's isolation work.

## 1. What exists [V = verified at `4d37280`]

- **D-26 is already built** (ADR-0047 "As built", 2026-10-01): `archeus/core/execution/pressure.py`;
  `live_work(conn)` in `archeus/core/application/live.py:54` with `context` and `handoff`, served
  as `/v1/status.live` (`archeus/api/routes.py:318`); gates CX-1…CX-18 in
  `tests/v1/unit/test_pressure_units.py`, `tests/v1/integration/test_context_capacity.py`;
  `tools/mutate_p21.py` (Z01–Z22). [V]
- **Own calls in flight are not in `live_work`** (`live.py:12` says so). The in-flight test exists
  for AP-1's concurrency count: `resources.own_call_live` (`archeus/core/application/resources.py:183`). [V]
- **`/v1/accounts`** returns each account's view, effective `resource_policy` and latest usage
  snapshot (`resources.py:646-652`, `routes.py:501`). No live consumers and no ledger totals,
  although `resources.ledger_totals` (`resources.py:194`) computes the totals. [V]
- **Provenance:** `Execution.model` exists (`archeus/core/domain/entities.py:975`); no
  `model_revision`, `served_model`, `task_family` or `capability_snapshot` anywhere in `archeus/`
  (grep). `RouteDecision.input_snapshot` exists (`entities.py:1573`, `core/routing/router.py`). [V]
- **Artifacts** are content-addressed blobs only (`entities.py:1271`): no producer record and no
  `artifact.recorded` event (grep). ADR-0047 clause 5(ii) therefore passes progress artifacts
  empty (ADR-0047 "As built"). [V]
- **Decision records:** `RouteDecision`, `PolicyDecision`, `UsageLedger`, `UsageSnapshot`,
  `AutomationRun` (`entities.py:1573, 1705, 1532, 1503, 1817`); `/v1/events`,
  the event stream and a mission timeline (`routes.py:187, 197, 590`). No trace view and no
  decision-log read. [V]
- **Health:** `/v1/health` read by Control → About (`clients/app/src/surfaces/Control.tsx:869`).
  No `metrics_daily` table, no metrics read, no Health section beyond Core's state. [V]
- **Diagnostics:** `core.log` is a plain `logging.FileHandler` (`archeus/core/runtime.py:526`), no
  rotation. No `doctor` verb: `archeus/cli/main.py:27` lists the verbs. [V]
- **Command bar:** `clients/app/src/state/palette.ts:57` filters client-side; no Core search. [V]
- **Notifications:** the Qt shell has a tray (`claude_sessions/gui_qt.py:194`) and uses
  `showMessage` only to report its own tray actions, e-stop and Pause all (`gui_qt.py:253-266`); no attention or e-stop
  notification while hidden, no push. [V]
- **Schedule triggers:** refused by `archeus/core/automation/matcher.py:43` ("schedule and
  condition triggers are not built: p14-design-gate D14"); no `next_run`. [V]
- **Activity chip:** no Core record of an execution's current action (r13 §5; grep). [V]

## 2. Contradictions this gate cannot resolve alone

Classified after Codex's review (`.collab/reviews/T-117-474815f.md` finding 4). Only a *genuine*
conflict or a change of an approved order needs an owner amendment; the rest are recorded here.

| # | Item | Sources | Kind | Resolution | Owner amendment? |
|---|---|---|---|---|---|
| X1 | P21 "not started" yet its D-26 slice is built | p20 §5 K vs ADR-0047 "As built", testing-strategy §10 | historical sequencing | D-26 is recorded as a named exception, built ahead of order by the owner's D-26 decision (ADR-0047); it is not a general permission. Any further overlap is D0's | no (D0 is the amendment for further overlap, decided) |
| X2 | Notifications owner | ADR-0030 §4 says P20; p20 D8 (the user, 2026-10-05) moved them to P21 | stale text, superseded by approved p20 D8 | P21 owns them by p20 D8; an appended note on ADR-0030 is optional housekeeping | no |
| X3 | Two gates called G6 | testing-strategy §2 G6 (security, P20 K) vs the orchestration gates table G6 "one live derivation" | genuine identifier collision | this gate always writes "testing-strategy G6" or "orchestration G6"; renaming either is the owner's optional text edit | no (qualified references suffice) |
| X4 | Where Health lives | plan §28 "Control → About → Health" vs §31.1 P21 "Health page" | compatible wording | Health is Control → About → Health; no new destination | no |
| X5 | Schedule triggers and `next_run` | ADR-0030 §4 assigns them to P21; plan §31.1 P21 omits them; p14 D14 deferred them | omitted plan coverage; ADR-0030 already decides P21 ownership | in P21's scope by ADR-0030 (D9) | only if D9 (b) defers them |
| X6 | `live_work` and own calls | plan §28 row vs `live.py:12` (not built) | acknowledged unfinished scope (ADR-0043:26-32) | slice B builds it (orchestration G6, G8) | no |

## 3. Scope

In: ADR-0031 §6 provenance; ADR-0030's producer record and `artifact.recorded`; ADR-0043's own
calls in `live_work`, account consumption and the `status` verb in words; the trace view and `why`
(R13-05 if D10 assigns it); `metrics_daily` and Health; `archeus doctor`; `core.log` rotation;
the activity chip's Core record; server-side command-bar search (D-12); OS notifications (p20 D8);
K5 requirement provenance and K7 Attention items (orchestration plan; D11, D12); event causation
for every command and the trace's lanes, call→result pairing and two clocks (D13, D14); whatever D9
and D10 add. Out: routing behaviour, Codex (P23), Resources UI and project defaults
(P22), push transports unless D1 picks one, PV-20.

## 4. Decisions requiring approval

### D0 — Order against P20 — **DECIDED (the owner, 2026-10-19)**
- Asked (AskUserQuestion, verbatim): "P21 overlap (D0): the plan says P21 "Depends: P20". Amend it so named P21 slices can be BUILT while P20's G/K are still open?"
- Answer (verbatim): "Allow named safe slices (Recommended)". The option chosen read, verbatim: "Amendment: P21 slices that touch no isolation, boundary, credential or auth code (notifications, metrics_daily, trace view, search, doctor, provenance records) may be built now; every P20 security gate (G6, no High open, slice G) stays required; P21 cannot be declared complete before P20 is. Each slice still needs its own approved decisions."
- **Eligible to be built before P20 completes**, exactly the owner's list: notifications (slice G),
  `metrics_daily` and `archeus doctor` (slice D), the trace view (slice C), search (slice F),
  provenance records (slice A). **Not eligible** until P20 completes or the owner names them:
  slice B (`live_work` own calls, `/v1/accounts` consumption), slice E (the activity chip, which
  reads the PreToolUse request at the execution boundary), slice H (schedule triggers), and the
  Health page's Attention items (D12).
- Every P20 security gate stays required (testing-strategy G6, no High finding open, slice G);
  P21 cannot be declared complete before P20 is; each slice still needs its own approved decisions
  below. The plan's P21 entry carries this as a dated appended amendment; "Depends: P20" is not
  reworded.

### D1 — Notifications (p20 D8)
- **(a)** OS notification only: the Qt tray's existing `showMessage` on approval required and
  e-stop while the window is hidden; push recorded as deferred to V1.x. **(b)** (a) plus a push
  relay (ntfy): a third-party surface, needs its own threat-model entry. **(c)** Defer all.
- **Recommendation: (a).** No new dependency or external surface.

### D2 — `metrics_daily`
- **(a)** A table written nightly by a Core consumer, as plan §28 says. **(b)** Computed on read
  from the event log and ledger, no table.
- (a) costs a migration and a consumer; (b) costs read time that grows with history.
- **Recommendation: (a)**, with the metric list exactly as plan §28 names it.

### D3 — Trace view and decision log
- **(a)** A per-mission trace read joining events (`cause_chain`), decisions and checkpoints; the
  unified decision log stays a client approximation (ADR-0030 §4 calls it optional). **(b)** (a)
  plus a Core decision-log read. **Recommendation: (a).**

### D4 — Provenance levels (ADR-0031 §6)
- **(a)** Record `model_revision` and `served_model` with REQUESTED / ROUTED / SERVED now; BILLED
  only when an adapter's usage attributes the model. **(b)** All four levels required now.
- **Recommendation: (a)**; a level is never claimed without its source.

### D5 — The artifact producer record
- **(a)** Build it in P21 (ADR-0030 §4) and feed ADR-0047 clause 5(ii) with it. **(b)** Defer;
  progress stays end-state only. **Recommendation: (a)**; it closes an "As built" gap.

### D6 — Activity chip's record
- **(a)** Core records an execution's current action from the PreToolUse request it already
  judges (the canonical action, no raw input); the chip reads it. **(b)** Move the chip to P23.
- (a) must not store raw tool input (slice I's secrets inventory, I-F4). **Recommendation: (a).**

### D7 — Command-bar search (D-12)
- **(a)** A Core read over mission, project and knowledge titles (`/v1/search`), the client
  filter kept as the offline fallback. **(b)** Keep client-only. **Recommendation: (a).**

### D8 — `archeus doctor` and log rotation
- **(a)** A read-only verb checking DB integrity, consumer lag, stuck executions and hook
  installation (plan §28), exit code per finding; `core.log` gets stdlib `RotatingFileHandler`.
  **(b)** (a) plus `--fix`. **Recommendation: (a)**; repair stays explicit commands.

### D9 — Schedule triggers and `next_run` (X5)
- **(a)** Build them in P21 as ADR-0020 decided. **(b)** Record them as V1.x with the user as
  owner. **Recommendation: decide explicitly**; (a) if V1 should run anything on a clock, else (b).

### D10 — R13 rows (p20 D11, undecided)
- **(a)** Accept p20 D11's P21 rows: R13-03 digest rows, R13-05 `why this mission?`, R13-06
  `status` in words. **(b)** Other owners. **Recommendation: (a).**

### D11 — Requirement provenance (K5; orchestration plan §K, lines 551, 624)
- Each RouteDecision requirement records where it came from ("classified as"):
  `requirements._source` per requirement. **(a)** Record `_source` on every requirement at
  decision time (classifier, plan contract, user override, project default), read-only in the
  trace. **(b)** Record only for classifier-derived requirements.
- Slice A (provenance records): **eligible** under D0. **Recommendation: (a)**; a requirement
  without a source cannot be explained in §28.

### D12 — Attention gap (K7; orchestration plan lines 553, 624, 650, D-11 "yes")
- Attention items for LIMITED / DEGRADED / OPEN accounts and resource-blocked missions, decided
  for P21 by D-11. **(a)** Derive them in Core from account and mission state into the existing
  Attention read; the Health page links to them. **(b)** Client-only derivation from `/v1/accounts`.
- Slice D (Health): **not eligible** under D0 (account state is not on the owner's list).
  **Recommendation: (a)**, one derivation in Core (orchestration G6's "one live derivation").

### D13 — Event causation for non-automation commands (ADR-0030 §4 item 4)
- ADR-0030 assigns "event cause for non-automation commands" to P21; today only automation runs
  carry a cause, so `cause_chain` cannot explain a user's or Core's own command. **(a)** Every
  command records its cause (the request, approval, timer or event that issued it) in the event
  the writer appends; the trace reads it. **(b)** Only commands issued from an event or an
  approval carry a cause; a direct user command is its own root.
- Slice C splits in two. **C-read** (the trace view reading causes that exist): **eligible** under
  D0. **C-write** (the command writer recording a cause): it changes the event payload of every
  command, so it is eligible under D0 only after a file-scope check shows its diff touches no
  isolation, boundary, credential or auth code (the writer, the commands it records, nothing in
  `archeus/node/isolation.py`, the hook, `authorization.py` or the credential paths); if the check
  cannot show that, C-write waits for P20 or for the owner's explicit authorization. An aimed
  review alone does not satisfy D0's condition. **Recommendation: (b)**, it closes the gap without
  inventing a cause for a root action.

### D14 — Trace lanes, call→result pairing, replay with two clocks (p16 §20.16 G12/G13; ADR-0030 §4 item 4)
- p16 defers G12/G13 to P21: "a trace view builder over D4's normalised events reusing
  flowgraph's lane and call→result pairing"; ADR-0030 asks for "the trace/replay view, content
  time ≠ presentation time". **(a)** Within each execution's trace, lanes are the sidechains of
  that execution's transcript (p16-design-gate.md:960, as flowgraph draws them), each tool call
  paired to its result inside its lane, and the trace replayable on its own clock (event time)
  separate from the playback clock. **(b)** Sidechain lanes and pairing now; replay recorded as
  V1.x.
- Slice C: **eligible** under D0. **Recommendation: (a)**; replay over recorded events needs no
  new record and is what both sources ask.

### 4.1 Decisions taken (the owner, 2026-10-19)

Asked with the draft at `f02cec7`; answers verbatim from the owner's AskUserQuestion answers:

- **D0**: "Allow named safe slices (Recommended)" (recorded above and appended to the plan).
- **D1-D8, D10-D14**: "Approve all recommendations (Recommended)". Each takes the option this gate
  recommends: D1 (a), D2 (a), D3 (a), D4 (a), D5 (a), D6 (a), D7 (a), D8 (a), D10 (a), D11 (a),
  D12 (a), D13 (b) with the C-write file-scope condition, D14 (a).
- **D9**: "Build in P21". Schedule triggers and `next_run` are built in P21 (slice H, ADR-0030 §4);
  slice H is not in D0's eligible set, so it waits for P20.

Slices eligible now under D0: A (provenance, D4/D11), C-read (trace view, D3/D14), D's
`metrics_daily` and `archeus doctor` (D2/D8), F (search, D7), G (notifications, D1). C-write (D13)
after its file-scope check. B, E, H and the Attention items (D12) wait for P20.

### 4.2 Owner decision: "Accept stopped" (2026-10-22, T-127 review of 5586c06)

The Core reports a worker the launch never started (plan, policy, verify, automation, metrics
when absent) as `stopped`, not `idle` (runtime.py Health, H08/H10). The owner decided to accept
`stopped` as a ready state, for the two workers a launch may leave unwired: `plan` (no brain port)
and `verify` (no verifier or reviewer port). `tools/v1_env.py` `UNWIRED` names them, and `not_ready`
treats `stopped` as ready only for those. Any other `stopped` component (engine, knowledge, intent,
policy, automation, world, exec, metrics) is not ready. A `failed` component stays not ready. The
judge's settle check (`tests/v1/judge/http.py` `_idle`) accepts `stopped` for `plan` and `verify`
only. An engine whose writer closed reads `failed`, not `stopped` (runtime.py, H12).

## 5. Slices and order (after approval)

0. **D-26** — built (X1).
1. **A** provenance (D4, D11) and the producer record (D5); `artifact.recorded`. *(D0-eligible)*
2. **B** own calls in `live_work`; `/v1/accounts` consumption (live consumers, `ledger_totals`,
   windows with unknown kept unknown); `status` in words (R13-06). Gates orchestration G6, G8,
   G12, G13 (P21 half).
3. **C** trace view and `why` (D3, D13, D14, R13-05); R13-03 digest rows. *(D0-eligible)*
4. **D** `metrics_daily` (D2), `archeus doctor` and rotation (D8) *(D0-eligible)*; Control →
   About → Health and its Attention items (D12) *(not eligible before P20)*.
5. **E** activity chip (D6).
6. **F** command-bar search (D7). *(D0-eligible)*
7. **G** OS notifications (D1). *(D0-eligible)*
8. **H** schedule triggers (only if D9 (a)).
9. **K** §28 walk-through from the UI, full verification, P21 as built; report and stop.

Each slice: its own commits, targeted tests, the relevant E2E, client tests when the SPA changes,
design and traceability gates, its mutants (`tools/mutate_p21.py`, ids after Z22).

## 6. Data model and storage impact

`Execution`: `model_revision`, `served_model`, its level, current action (D6). `RouteDecision`
`input_snapshot`: harness `installed_version`, catalogue row versions; decision `task_family`,
`capability_snapshot` (empty). New: artifact producer record; `metrics_daily` (D2); trigger
schedule state (D9 (a)). Each is a numbered migration with a pre-migration backup, as AP-1's.

## 7. API, CLI, UI and TUI impact

`/v1/status.live` gains own-call items; `/v1/accounts` gains consumption; new reads for the trace,
metrics and search (D3, D2, D7); `archeus doctor` (D8); the `status` verb in words. SPA: Health
under Control → About, the trace view, the activity chip, Core-backed command bar. TUI: `status`
and `doctor` output only. `generated.ts` and the API reference regenerate.

## 8. Failure modes and races

A reading that is missing renders unknown, never 0 (G12, ADR-0047). An own call past its maximum
run leaves `live_work` (ADR-0048 D-25.4). `metrics_daily` recomputes an incomplete day rather than
appending. A notification never carries an approval's content beyond its title. `doctor` holds no
write lock.

## 9. Security

New reads stay behind the existing scopes (`observe`); search returns titles the caller may
already read. The current-action record stores the canonical action, never raw tool input
(I-F4). D1 (b) would add a third-party relay and needs its own threat-model entry first. No
change to credentials, the boundary or PV-20.

## 10. Evidence required before P21 is declared complete

- Every plan §28 question answered from the UI, walked through and recorded.
- Orchestration G6, G8, G12 and G13 (P21 half) pass; CX-1…CX-18 still pass.
- Every new mutant killed (`tools/mutate_p21.py`); Z01–Z22 re-run.
- Full `tests/v1` with E2E; client type check and unit tests; `gen_ui.py --check`;
  `gen_api_docs.py --check`; traceability and design gates.
- No `phase:P21` xfail left.

## 11. Deviations declared up front

- D-26 was built before P21 opened (X1).
- If D0 (b) is approved, P21 slices land while P20 is open; P20's exit record is unaffected.

## 12. As built

### 12.A Slice A — provenance (D4, D11) and the producer record (D5)

1. **Served model (D4, ADR-0031 §6).** `Execution` gains `served_model`, `served_level`
   (`entities.PROVENANCE_LEVELS`: REQUESTED < ROUTED < SERVED < BILLED) and `model_revision`.
   `work.new_execution` records REQUESTED from the route's model. The Claude Code adapter emits a
   `model` event from each assistant message's `model` (never `<synthetic>`, Claude Code's own
   stand-in) and lists the result's `modelUsage` keys as `billed`. The manager turns a `model`
   event into SERVED and a result into BILLED when the usage attributes the served model, or
   attributes exactly one model (`manager._billed`); `executions._served` never lowers a level
   and names `model_revision` only at SERVED or BILLED. ROUTED has no source yet (no proxy adapter
   reports its choice), so it is never claimed.
2. **Snapshot fields (ADR-0031 §6, ADR-0033 §2).** Each harness in a decision's `input_snapshot`
   carries `installed_version` (`HarnessInfo.version`; None while the adapter does not probe it,
   as Claude Code's does not). `RouteDecision` gains `task_family` (None: no family exists before
   ADR-0032, V1.x-O1) and `capability_snapshot` (`{}`: no evidence is read before V1.x-O2), both
   frozen. Catalogue row versions are not recorded: no versioned catalogue row exists before P22
   (ADR-0031 §4), so there is nothing to read. Routing is unchanged; a decision still replays to
   itself.
3. **Requirement provenance (D11, K5).** `call_snapshot` and `task_snapshot` record
   `requirements._source`, one source (`resources.REQ_SOURCES`) per requirement key; the identity
   keys (`resources.REQ_IDENTITY`) carry none. The router does not read it.
4. **Producer record (D5, ADR-0034 §1).** `ArtifactRecord` (prefix `arc`, migration
   `0017_artifact_records.sql`, immutable) names the artifact's sha256, the producing execution,
   its kind (`entities.ARTIFACT_KINDS`), task, mission and label. `executions.record_artifact`
   inserts the Artifact row when the bytes are new, the record and `artifact.recorded`.
   `checkpoint.derive` records every checkpoint it writes. `executions.view` returns an
   execution's `artifacts`.
5. **ADR-0047 clause 5 (ii).** `no_progress` passes the artifacts the execution recorded to
   `pressure.progressed`; its own checkpoint is derived after the guard, so a checkpoint never
   counts as progress.
6. **Tests and mutants.** `test_I_H3_every_recorded_requirement_names_its_source`,
   `test_E33b_the_served_model_is_recorded_at_the_level_its_source_supports`,
   `test_a_provenance_level_is_never_lowered_and_names_a_revision_only_from_its_source`,
   `test_an_artifact_the_continuation_produced_is_progress_and_a_checkpoint_never_is`,
   `test_an_artifact_record_names_a_sha256_produced_by_an_execution`, the adapter contract's
   provenance lines; `tools/mutate_p21.py` Z23–Z29.
7. **Scope (D0).** No isolation, boundary, credential or auth file is touched: the slice changes
   the domain entities, the execution and routing application layer, the checkpoint writer, the
   execution manager's stream reading, the Claude Code adapter's stream normaliser, one migration,
   the API schema and the generated client types.

### Slice D as built (2026-10-19, card T-120)

The D0-eligible part of slice D: `metrics_daily` (D2), `archeus doctor` and `core.log` rotation
(D8). Control -> About -> Health and its Attention items (D12) are not built: they wait for P20.

- **`metrics_daily`** (migration `0018_metrics_daily.sql`, after slice A's `0017_artifact_records.sql`;
  slice D is built on slice A's line because `migrate.migrations()` refuses a gap): one row per
  finished UTC day, `(day, metrics JSON, computed_at)`. `archeus/core/metrics.py`: `compute(conn,
  day)` reads only what Core already recorded and returns the plan section 28 figures - missions
  completed and failed (`mission.state_changed` to COMPLETED/FAILED that day), median time to
  complete (completion event minus the mission's `created_at`), approvals per ended mission,
  fallback rate (route decisions that day, `fallback` over `selected` + `fallback`), verification
  failure rate (`verification.state_changed` to FAILED over PASSED + FAILED), cost per mission band
  (the latest plan's `estimated_cost`, else `unknown`; the mean of reported `cost_usd` from the
  usage ledger by execution or route decision) and context tokens per task kind (a task route
  decision's context package `budget.used_tokens`, by the task's `kind`). A figure with nothing to
  measure is None, never 0 (ADR-0048 D-25.3's rule).
- **The worker**: `Metrics` runs as the `archeus-metrics` WorldLoop beside the other workers; each
  pass fills the oldest finished day without a row, from the first event's day to yesterday. A day
  is written once (`INSERT ... ON CONFLICT (day) DO NOTHING`) and never rewritten; today is never
  computed. WorldLoop runs a pass after every commit, so once every finished day has its row the
  worker remembers the date and reads nothing until it changes. Its write is `metrics.record`, a writer command, and `core/metrics.py` joins the
  structural writer-module list in `test_db_schema.py` (written as a plain `INSERT INTO` so that
  gate sees it: its regex does not match `INSERT OR IGNORE INTO`, recorded below).
- **`archeus doctor`** (`archeus/core/doctor.py`; `archeus/cli/main.py` and
  `claude_sessions/cli.py`'s `V1_VERBS` only dispatch to it, so the CLI still imports no database
  path - L1, `test_api_structure.py`): integrity (`PRAGMA integrity_check`), schema version against
  the migrations, consumer lag over 1000 events, executions unfinished and untouched for 6 hours,
  and the execution hook (`manager.HOOK` exists and compiles). It prints one line per check,
  `FINDING ...` for each finding, and exits with the OR of the findings' bits (database 1, schema
  2, lag 4, stuck 8, hook 16; 0: nothing found). It has no `--fix`, never starts Core, never reads a
  credential and prints only ids, counts and paths. It opens the database through the new
  `connection.inspect` (URI `mode=ro`): a `query_only` reader that closes last checkpoints a WAL
  into the file, which would rewrite a database Core crashed out of. SQLite may leave its own
  empty `-wal` and a rebuilt `-shm` index beside the file; the database file and the WAL's data are
  unchanged (tested on a copied crash-left WAL).
- **Rotation**: `core.log` is a `RotatingFileHandler`, 5 MB, three old files (`LOG_BYTES`,
  `LOG_BACKUPS` in `runtime.py`).
- **Tests**: `tests/v1/integration/test_p21_metrics_doctor.py` (nine); `test_db_schema.py`
  follows the new table and derives the latest schema instead of naming 16.
- **Mutants**: Z40-Z47 in `tools/mutate_p21.py` (a day computed before it ends; unknown written as
  0; a day rewritten; doctor through a checkpointing connection; doctor creating the database;
  every unfinished execution stuck; lag never reported; rotation removed), Z48-Z49 (the worker
  scanning the log after every commit once filled; a broken hook never reported).
- **Not built here, recorded**: the worker is not in `/v1/health` (no reader needs it before
  Health, D12); nothing reads `metrics_daily` yet (Health, D12). `events.at` has no index, so each
  computed day scans the log (a `ponytail:` note in `metrics.py`).
- **Found outside this slice, not changed**: `test_db_schema`'s writer gate does not see
  `INSERT OR IGNORE INTO` (`consumers.py` passes it only because the same file also has a plain
  `INSERT INTO`); `tests/v1/unit/test_tool_removal_units.py::test_F10_...` fails at `b01dc32`
  already, on `LS` (T-113's per-tool path field).
### Slice F as built (2026-10-19, card T-121)

- **Core search (D7 (a)).** `GET /v1/search?q=` (`search_titles` in `archeus/api/routes.py`,
  `queries.search` in `archeus/core/application/queries.py`, response `SearchResult` in
  `archeus/api/schemas.py`): missions, projects and knowledge items whose title (a project's
  name) holds the needle, case ignored, at most 20 of each. The same rows `/v1/missions`,
  `/v1/projects` and `/v1/knowledge` answer, under the same `observe` scope, cut to id and
  title (plus a mission's state and version, which the bar's Pause/Resume need): never a body.
  A needle that is blank after trimming or longer than 200 characters is `400 invalid_request`.
- **No migration.** The scan is three table reads filtered in Python (`ponytail:` note at the
  site: an index when titles number in the tens of thousands); 0019 stays unused.
- **The command bar** (`clients/app/src/surfaces/CommandBar.tsx`) reads `/v1/search` while it is
  connected and a needle is typed, and uses Core's lists in place of its own; offline it keeps
  the lists it has already read and sends no search. `palette.ts` is unchanged in logic.
- **Generated:** `generated.ts`, `archeus/cli/_api.py` and the API reference regenerated;
  `tools/gen_api_docs.py` gained the `q` query type.
- **Tests:** `tests/v1/integration/test_p21_search.py` F01 (case, the three kinds, ids and titles
  only, no body), F02 (blank and long needles), F03 (a device without `observe` gets
  `403 scope_required`, no token `401`, neither sees a title); `tests/v1/e2e/test_spa_palette.py`
  now asserts that typing asks Core, that a hit only Core answered is shown, and that offline no
  search is sent (it used to assert that typing sent nothing, the P19.5 behaviour D7 replaces).
- **Mutants:** Z50-Z56, each killed by the test it names.

### Slice G as built (2026-10-19, card T-121)

- **OS notifications (D1 (a)).** While the Qt shell's window is hidden to the tray, and only
  then, a `QTimer` in `claude_sessions/gui_qt.py` calls `Shell.notices` every
  `NOTICE_EVERY_S` (10) seconds; showing the window stops it. `Shell.notices`
  (`archeus/cli/gui.py`) reads `/v1/events` after the last head with the shell's own
  `observe` + `control` credential (item 86's, unchanged) and returns what to say.
- **What is said.** `gui.notice`: for `approval.requested`, "A <kind> waits for your
  decision", the kind mapped through a fixed word list (`APPROVAL_WORDS`; an unknown kind is
  "request"); for `core.estopped`, a fixed sentence. Nothing else of an event is ever said: no
  mission title, no command, no tool input (§8: "never ... beyond its title"; an approval has
  no title, so the kind is all it says).
- **Once, from now.** The head is read when the window hides, so nothing older is said; each
  event is said once; with Core unreadable the tray is silent and keeps its head. Push stays
  deferred (V1.x).
- **No new credential, route or scope.** The shell's credential already held `observe`.
- **Tests:** `tests/v1/integration/test_gui_shell.py` G01 (a real Core: an approval asked
  before the head is not said, one asked after is said by kind with neither the mission title
  nor a token from it, an e-stop is said, nothing twice, Core down is silence) and G02 (a payload
  carrying a command and an unknown kind is said as "request"). The real-Qt
  `tests/v1/e2e/test_gui_qt.py` still passes; it does not hide the window, so the timer itself is
  exercised only through `Shell.notices`.
- **Mutants:** Z57-Z59, each killed by the test it names.

### Found while building F and G

- `tests/v1/unit/test_mutation_suites_parse.py` listed suites up to `mutate_p20`, so
  `tools/mutate_p21.py` was never parse-checked, and K3's rename of `guarded` to `refused` in
  `executions.py` had left Z13 and Z14 anchored on text that no longer existed. Both re-anchored
  to the same decision (`refused is not None`) and killed; the suite now runs on
  `tools/mutate_p18.py`'s runner (SPA rebuild for a browser-guarded mutant); Z01-Z22 20/20 and
  Z13, Z14 killed under it.
- `tests/v1/unit/test_api_structure.py` pins the route table to the per-phase tables; slice F's
  `GET /v1/search` (`observe`) is its `P21` table (added after the recovery, 2026-10-19).
### Slice C-read as built (2026-10-19, card T-119)

C-read only: the trace view reads the causes that exist. C-write (D13, the command writer recording
a cause) is not built; its file-scope check (`.collab/T-119-cwrite-scope.md`) finds that
approval-issued causes need `authorization.py`, so it waits for P20 or the owner's explicit word.

- **The trace (D3 (a), D14 (a)).** `GET /v1/missions/{id}/trace` (`mission_trace` in
  `archeus/api/routes.py`, `observe` scope like the timeline; `404` for an unknown mission),
  built by `archeus/core/application/trace.py`: the mission's events oldest first with their
  `cause_chain` (the timeline's read, at most 1000, `truncated` when more exist), its policy and
  route decisions, and per execution its checkpoints and its output folded into lanes. Nothing is
  written. The output is the execution tab's own redacted read (`execution/output.py`); a tool
  call's input is never carried, only its name.
- **Lanes and pairing.** A lane is a transcript sidechain: the Claude Code adapter's `normalise`
  now keeps `parent_tool_use_id` as `lane`, the call's `id` and the result's `tool_use_id`
  (`archeus/harnesses/claude_code/adapter.py`; a read of the stream, no change to how anything is
  launched or judged). `trace.lanes` puts each step in its lane (`main` for the conversation),
  pairs a call with its result by id inside the lane, and names the step that spawned a sidechain.
- **Two clocks (D14).** The SPA's Trace tab (`clients/app/src/surfaces/Mission.tsx`, between
  Timeline and Relations; key `c` in the TUI) shows each event at its own time and replays them
  one by one, waiting the gap between two events at 1x, 10x or 100x, clamped to 50 ms-1.5 s; at
  the end it returns to the live list. The TUI tab lists the same trace without a replay.
- **R13-05.** A bare `why` in a mission's thread is the grammar's (`grammar.py`): "This mission
  exists because <origin>: "<objective>"", with the mission as its card (`conversation.py`
  `_why(bare=True)`); outside a thread it stays the brain's. A declined reading no longer cites an
  ADR to the user.
- **R13-03.** The digest names no message rows (`archeus/core/world/digest.py`): a mission
  thread's messages fold into the mission's row, the primary conversation's into one
  `new_messages` row that counts messages, ordered last; the SPA's Now and the TUI say
  "N new messages".
- **Generated:** `generated.ts`, `archeus/cli/_api.py`, the API reference and the navigation
  tokens (`Trace` tab).
- **Tests:** `tests/v1/integration/test_trace.py` (seven: pairing inside a sidechain lane, the
  Claude stream's ids and lane, the trace read with a redaction check, the route and its 404, the
  bare `why`, no ADR in a declined reading, the digest folding); `tests/v1/e2e/test_spa_trace.py`
  (the tab replays every event from the first, in a real browser); `clients/app/test/shell.test.ts`
  (tab order).
- **Mutants:** Z30-Z39 in `tools/mutate_p21.py`, each killed by the test it names.

### Slice D Health as built (2026-10-21, card T-127)

Built under the owner's 2026-10-21 answer naming the not-yet-eligible P21 pieces (the board, "Owner
2026-10-21", verbatim: "Yes, all five (Recommended)"): Control -> About -> Health and its Attention
items, D12 (a). "P21 cannot be declared complete before P20 is" (D0) is unchanged.

- **Attention items (D12 (a), K7, D-11)**, derived in Core into the existing `/v1/attention` read
  (`archeus/core/application/attention.py`), with no new kind and no stored row:
  - an Account in LIMITED, DEGRADED or OPEN is an `account` item beside UNAUTHENTICATED's, reason
    code `limited` / `degraded` / `open` (`reauth` unchanged), its label as the reason; a LIMITED
    one also carries `until` (the account's `limited_until`);
  - a **resource-blocked mission** is a `mission` item, reason code `no_resource`: a mission
    BLOCKED from EXECUTING with a BLOCKED task whose **latest** route decision has result `blocked`
    (P10: routing found no eligible resource and blocked the task and its mission). The reason is
    that route's own explanation and the item carries its `unblock_at`. A task BLOCKED by a
    rejected route approval (its last route asked), a mission held from another state, and a
    mission whose last route did find a resource are not listed. A mission already listed for
    `planning_blocked` is not listed twice.
- **The metrics read (D2)**: `GET /v1/metrics?days=N` (observe, 1..90, default 14;
  `metrics.daily`): the newest finished days of `metrics_daily`, newest first, each figure as
  recorded, so an unknown stays null. Schema `MetricsDaily`; `generated.ts`, `_api.py` and the API
  reference regenerated. `/v1/health` gains `metrics`, the `archeus-metrics` worker's state (slice D
  had left it out until a reader needed it).
- **SPA**: Control -> About gains a **Health** section between This Core and This client: the
  account and no-resource items (state badge, label, reason, linked to Control -> Resources or the
  mission), then the last seven finished UTC days (completed, failed, median time to complete,
  approvals per mission, fallback rate, verification failures; null shows "unknown", never 0) and,
  for the newest day, cost per mission band and context tokens per task kind. The Workers line
  names `metrics`. Attention and Now name an item by its reason where the reason changes what it
  is ("Account at its usage limit", "Account failing", "Account stopped after repeated errors",
  "No resource can run this mission"); a LIMITED account says when it resets. The TUI's Attention
  says the same words (`screens.ATTENTION_REASON`); it has no Health page (§7: status and doctor
  only).
- **Not built, recorded**: `/v1/metrics` has no invalidation rule because writing a day appends
  no event: the section reads it when opened. No browser test drives the Health section (the
  owner's PC rule keeps e2e to the integration run, T-130). The `Health` schema is closed and
  already lacked `exec`, `verify` and `automation`, which `/v1/health` returns; not changed here.
- **Client helpers**: the item labels (`attentionLabel`, with the kind words it falls back to) and
  the Health formatters (`known`, `pct`, `spanText`) live in `clients/app/src/state/present.ts`, the
  pure module the node tests run, so `clients/app/test/health.test.ts` pins them: a reason naming
  its item, "unknown" against a measured 0, the minutes and hours split.
- **Tests**: `tests/v1/integration/test_p21_health.py` (H01-H06); `test_api_structure.py`'s P21
  table gains the route; `tests/v1/tui/test_acceptance.py` (the TUI's labels); the node suite
  (249 pass, `tsc --noEmit` clean).
- **Found while building, fixed**: `test_guards.py`'s textual scan of the application layer read
  the `state=` keyword in `_no_resource`'s read filter as a state write; the filter now passes the
  column through `**{'state': ...}`, the form `attention()` already uses (no change in what it reads).
- **Mutants**: Z80-Z89 in `tools/mutate_p21.py` (LIMITED or OPEN accounts dropped, `until`
  dropped, the first route deciding instead of the last, an asking route taken for no resource, a
  mission held from verification listed, the route's reason dropped, the days oldest first, the
  days unbounded, the TUI naming only the kind), Z120-Z122 (the first blocked route deciding when
  another blocked task has no resource route, a never-started metrics worker reading idle, the
  no-resource item dropping `unblock_at`), Z160-Z165 (a dict-spelled state write outside a read, a
  never-started plan, policy, verify or automation worker reading idle, a past reset read as
  "resets" in the TUI).
- **Review fixes (independent review of 8cd47d1, `.collab/reviews/T-127-8cd47d1.claude.md`)**:
  - The Health empty state said every account can work. DISABLED and UNVERIFIED accounts raise no
    item, and with no accounts the claim is vacuous, so it now says only what Attention knows: no
    account has stopped or needs you, and no mission waits for a resource (`clients/app/test/health.test.ts`).
  - A metrics worker that was never started reads `stopped`, not `idle` (`runtime.py`; H08).
  - `_no_resource` lists a mission only when every BLOCKED task's last route blocked on a
    resource, so a task stopped for another reason no longer gets the no-resource reason (H07).
  - Each nullable Health figure is checked in source to render through `known(`, so a raw render
    fails the node suite (`health.test.ts`). Browser coverage is still T-130's.
  - A limited account whose reset instant has passed reads "reset due", not "resets N min ago"
    (`resetText`).
  - The reason labels and the KIND labels are pinned equal to the TUI's `ATTENTION_REASON` and
    `ATTENTION_KIND` (H09). The TUI says "reset due" for a past reset too (`present.reset_text`).
  - Round 2 (review of 65d2d6d, `.collab/reviews/T-127-65d2d6d.claude.md`): the empty state now
    says "No account needs you" (it claimed no more than Attention lists). A never-started plan,
    policy, verify or automation worker reads `stopped`, as metrics does (H10). The state guard
    sees the dict spelling `**{'state': ...}` again: a line that sets a state through it is
    flagged unless it is a read (`rows.where(` on the same line) or planning.py's outcome dict,
    named by its exact text. The guard is not weakened; `test_the_state_guard_sees_the_dict_spelling_outside_a_read`
    pins it. The node suite checks that the nullable figures never render raw (`{d.<field>}`).
  - Not changed, on the review's reading: the per-read cost of the Attention scan (bounded by
    the blocked missions; a join is the upgrade if it grows). H05 and H06 are still weak (a schema
    check and an auth check); not strengthened here.
