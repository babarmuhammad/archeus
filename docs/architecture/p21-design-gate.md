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

### Slice B as built (2026-10-21, card T-125)

Built by the owner's naming of 2026-10-21 under D0 ("Yes, all five (Recommended)", recorded on
`.collab/BOARD.md` above T-125): own calls in `live_work`, each account's consumption in
`/v1/accounts`, and the `status` verb in words (R13-06). No migration.

- **Own calls in live work (ADR-0043 §2, ADR-0048 D-25.4; orchestration G6).**
  `archeus/core/application/live.py` `live_work(conn, project_id=None, now=None)` lists every
  execution in a live state, then every own call in flight, each oldest first. An own call is in
  flight while `resources.own_call_live` holds: no `outcome` yet, a `selected` or `fallback`
  result, and within its `max_run_s`. Its item is `kind: own_call` with its `purpose`, `source`,
  mission (only when the source is a mission that exists), project, harness, account,
  `account_ref`, model, effort and `started_at`; `state`, `task_id`, `attempt`, `handoff` and
  `context` are null, because an own call has none of them. `resources.own_calls(conn, now)` is
  the one scan of the last day's `archeus_call` decisions behind both `live_work` and
  `ledger_totals`, so an account's `running` and its listed consumers come from the same rows.
- **Own calls visible, still (G8).** Nothing animates an own call: Core writes no `execution.*`
  frame for one, and the SPA's `running()` (`clients/app/src/state/orbit.ts`) and the palette's
  `effectOf` (`state/palette.ts`) skip `kind: own_call`, so the halo, the strip's running count
  and "N running attempts pause" stay executions only. An item with no `kind` (an older reader's
  fixture) is still an execution there.
- **Consumption and effective policy (ADR-0043 §3, §4; G12, G13).** `resources.account_view`
  adds `consumers` (the account's `live_work` items), `ledger` (`ledger_totals` for today: tokens,
  cost, `running` and `complete`) and `policy` (`resources.effective_policy`, the dict the router's
  snapshot carries for the account, now built by the same function in `_registered`). `usage`
  stays the newest snapshot of each window or null. `/v1/accounts` computes `live_work` once for
  all accounts. Schemas: `Account` requires `policy`, `ledger`, `consumers`; new `Ledger` and
  `LedgerComplete`; `LiveItem.kind` is `execution | own_call` with the execution-only fields
  nullable.
- **Unknown stays unknown (G12).** Control -> Resources -> Accounts (SPA) and the TUI's accounts
  section gain two rows: "Running now" (`consumersText` / `consumers_text`: "t1 attempt 2; an own
  call for the knowledge extraction", or "nothing") and "Today" (`consumptionText` /
  `consumption_text`): a complete measure is its figure, an incomplete one with something reported
  is "at least <figure>", and an incomplete one with nothing reported is "tokens unknown" or "cost
  unknown", never 0. Both functions are held to parity (five new cases in
  `clients/app/test/fixtures/parity.json`).
- **`status` in words (R13-06).** `conversation._status` says each mission and execution state
  with the label the clients show (`_said`, from `archeus/core/domain/words.py`, generated from
  `presentation.json` by `tools/gen_ui.py`): "Ship the fix (Executing)", "t1 attempt 1 (Starting,
  context ...)". It lists own calls in flight as "an own call for the <purpose> (<account>)"; its
  links stay executions and missions.
- **Not built here, recorded.** ADR-0043 §3 also names ledger totals by period, mission and
  subject kind; the gate's slice B line names `ledger_totals`, so only today's totals are served.
  ADR-0041 §5's "which values are defaults" and the ordering rule are not in the read: G13's P21
  half is the parity with the router's input, which is what is served. The own-call scan covers
  the last day (the existing `ponytail:` bound, now in `own_calls`): an own call with no
  `max_run_s` older than a day drops out of both readers at once.
- **Tests.** `tests/v1/integration/test_p21_live.py` (nine: G6 x2, G8, G12 x2, G13, R13-06 x2, S3);
  `test_context_capacity.py` now expects "Running" in the status words; `tests/v1/tui/test_security.py`'s
  accounts fixture carries consumers and a ledger; `clients/app/test/orbit.test.ts` and
  `palette.test.ts` gain the own-call cases.
- **Mutants.** Z60-Z69 in `tools/mutate_p21.py`, each killed by the test it names (re-run after
  the rework). The rework's own mutants are Z130-Z142 (the coordinator's range for this rework;
  Z110-Z111 belong to T-126).

### Slice B rework after the independent review (T-125, `.collab/reviews/T-125-330c3fb.claude.md`)

The review's verdict was CHANGES. What changed, finding by finding:

- **R1 (Required): work in flight read as a complete zero.** `ledger_totals` still sums only the
  written usage, and it is what the router reads (`router.py` `_budgets`, which takes `complete` as
  "cannot be evaluated"), so it is unchanged. `account_view` now sets the view's `ledger.complete`
  to false while `running > 0`, and `consumption_text` / `consumptionText` say "tokens unknown
  (N running)" for a zero, "at least <figure>" for a figure. Test:
  `test_g12_work_in_flight_is_unknown_not_a_zero_and_accounts_lists_the_same`.
- **Open item, recorded (owner, 2026-10-21: "Record open item (Recommended)").** The router's
  token and cost budgets judge in-flight usage as complete, the same G12 gap one layer down. It is
  recorded in ADR-0048 §3 ("Open item"), with what the router does today and the risk. The router
  is not changed in P21 (ADR-0047 clause 12); the fix goes under its own routing card.
- **S1: the header counts attempts.** "N running" in the offline Now counts executions;
  own calls are "· N own calls in flight" (`liveCountText`, `present.test.ts`).
- **S2: the TUI usage line** is the SPA's `usageText` in Python (`usage_text`): a window not
  reported is "unknown", not `null`. Two parity cases with `usageText`.
- **S3: Core no longer imports the TUI.** Core has its own copy of the state words,
  `archeus/core/domain/words.py`, generated by `tools/gen_ui.py` from the same JSON as the TUI's
  `_tables.py`. Moving one shared copy was tried first and refused: `tests/v1/tui/test_boundaries.py`
  says the TUI imports no Core module. Test: `test_s3_core_never_imports_the_tui_and_says_the_same_words`
  (no `archeus.cli` import in Core; the two copies equal). `gen_ui --check` keeps them current.
- **S4: the scans.** `own_calls` filters `subject.kind` in SQL (`json_extract`), so no other
  decision's body is decoded. `live_work` and `live_counts` each read the live executions by state
  in SQL (`executions_by_state`, no finished execution is decoded), and each reads the day's own
  calls. `/v1/accounts` runs both once: four scans, whatever the account count, and each account
  adds one read of its own usage rows (`ledger_totals`). `refresh_ledgers` (the own-call writer)
  computes `live_counts` once for all its accounts. Ceiling, recorded: the day's `route_decisions`
  are still scanned by `created_at` (no index). An index is a migration; none was added (0019 is
  not taken), and the owner may ask for one.
- **Route-decision reads (review F1; owner, 2026-10-21: "Strip at read (Recommended)").**
  `queries.route_decisions` and `get_route_decision` pass each decision through `_public_decision`:
  the keys `home_ref` and `home_key` are dropped everywhere in it; a value that is a home in plain
  or canonical form (a snapshot ref, the chosen `account_ref`) becomes null; a value that only
  contains one (a default account's `<harness>:<canonical home>`) says "its home" in its place.
  The stored row keeps them, because the execution manager reads the stored snapshot for a default
  account's home (`execution/manager.py`). Test:
  `test_owner_2026_10_21_route_decision_reads_show_no_account_home`; mutants Z145-Z146.
  **Open for the owner (not changed here):** the status read (`/v1/status`, `live_work`) carries an
  own call's `account_ref`, which for a registered account is its home path; the same leak as the
  route-decision read, in a second observe read. Recommended: strip it at that read the same way.
- **Now map (review F2).** The live map's set is `attemptIds(status.data.live)` (`orbit.ts`): an own
  call is never a map node (G8). Test: `orbit.test.ts`; mutants Z148-Z149. The header count
  `liveCountText(status.live)` is pinned by a source check and mutant Z150 (review F4).
- **S5: mutant gaps.** Z130-Z142 cover the in-flight count, its account (Z131 books it to no
  account), the lapsed flip, the in-flight zero, the palette skip, the TS and Python in-flight
  text, the TUI usage line, the execution-only link filter, the summary-only consumers, the
  "(+N more)" count and the own-call SQL filter. The account filter inside `live_counts` for a
  single account is not observable (each read takes its own account's key), so it has no mutant:
  the reviewer's "account filter" claim is covered by Z131 instead.
- **S6: timing.** The "still within its run" check uses a call with `max_run_s=600`; the one-second
  call is only read at a time five seconds on.
- **S7: consumers are summaries.** `consumers` carry `CONSUMER_FIELDS` (kind, id, purpose,
  mission_id, task_key, state, attempt, account_id), typed by a new `Consumer` schema.
  `/v1/accounts` also carried `home_ref` (the account's config directory), shown under Details,
  which predates this slice. Owner, 2026-10-21: "Drop from the view (Recommended)". The accounts
  view now leaves out `home_ref` and `home_key`: `home_key` is the same path in canonical form
  (ADR-0048 D-25.2), and a view that kept it would still show the home. The adapters and Core's
  own reads take the home from the row, not from this view (`queries.get_account` is unchanged).
  The SPA's Details row is gone; the TUI never showed it. Test:
  `test_owner_2026_10_21_the_accounts_view_never_shows_an_account_home`; mutants Z143-Z144.
- **N1 (kept):** the one-day scan window stays; it follows no `max_run_s` yet, and today no own
  call has a bound longer than a day.
- **N2:** the consumption row reads "Today (UTC)".
- **N3:** `account_view` reads the current `ResourcePolicy` row through `effective_policy`: the
  policy the next decision would use. It is not the decision's stored `input_snapshot`. Only this
  gate section was reworded; commit 330c3fb's message is history and still says "decided from".
- **N4:** the "Running now" list in `status` says "(+N more)" past the ten it names.
