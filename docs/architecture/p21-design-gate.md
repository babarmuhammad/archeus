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

### Slice E as built (2026-10-21, card T-128; rework rounds 1 to 5)

Built under D0 by the owner's naming of 2026-10-21 ("Yes, all five (Recommended)", recorded on
the board): slice E touches the execution boundary's Core side, so it was not D0-eligible on
2026-10-19. D6 (a) as approved: Core records the current action from the request it already
judges; nothing is added to the hook. The owner's D6 decision of 2026-10-21 is "Queue it" for a
fourth chip on a row. The owner accepted the fail-closed unclassified change, and "Accept all three"
for the allowed-to-held changes of the BOARD (wget --post-data, curl --json, NODE_ENV=test npm test;
board note 9, 2026-10-21). The host bug is a separate card, T-143 (board note 9: "Separate card").

- **The record (D6 (a)).** `Execution.current_action` (`archeus/core/domain/entities.py`; the row
  is a JSON body, so no migration): `{action_class, label, decision, seq}`, written by `_hook_answer`
  in `archeus/core/application/executions.py` in the same transaction as `hook_seq` and the
  `execution.hook` event. `serve_hook` passes it only after the token check: a foreign request, a
  replayed or older sequence number, or one for an execution no longer STARTING/RUNNING never
  becomes it. It is recorded with Core's answer for every authentic request. The action named is the
  one that decided the answer: the first denied action, else the first asking one, else the first
  action (early halts name the first action). The field is the last action Core judged for the
  execution; it stays after the run ends, and the schema says so (`CurrentAction` in
  `archeus/api/schemas.py`, carried into the generated client and the API reference by
  `tools/gen_api_docs.py`).
- **The label (I-F4, §9): a closed vocabulary, never an argument.** A label is one of: a host, from a
  URL that names its scheme (`://`, or a leading `//`), after its userinfo, port, path, query and
  fragment are stripped, and only when it is letters, digits, dots and dashes (`clear_host` in
  `archeus/core/execution/canonical.py`). A host label that can carry a secret shows as an ellipsis:
  longer than 20 characters, or with a letter and a digit and longer than 4, or an all-digit label
  longer than 6. The rule applies to every label, the TLD and a dotless host included (review round 5,
  R5: `Ab3dEf9hIjK2LmN4OpQ7` reads "…", `h.example.sk3Kd9fLq2mZ8xRv7wT1` reads "h.example.…",
  `482913756.example` reads "….example"). `zq9Kt4mP.example` reads "….example"; the plain words stay
  (`api.example.co.uk` reads as is). Residual, accepted with Q3: a host label of plain letters still
  shows, and so does a 4-character token (`a1b2.example`, the rule's length of 4 is kept). A URL is
  named only when it is the one URL of the call, and that URL is not the word after a flag that may
  take a value (round 5, S3: `curl --socks5 http://u:pw9Kd2@p.example:1080 h.example/x` names no host,
  nor does `curl --proxy-header http://decoy.example h.example/x`). A flag is taken to take a value
  unless it is one of the curl and wget switches that take none (`_NO_VALUE_LETTERS`, `_NO_VALUE_LONG`).
  Two such URLs, or one after a value-taking flag, name no host. Otherwise a tool and a verb from a short list for that tool (`_TOOLS` and `_VERBS` in
  `executions.py`; a program outside the list reads "a program"), or a fixed phrase: "shell" or
  "command" (the canonicaliser's own words), "search" (WebSearch), "a file in the workspace", "a file
  outside the workspace" (a path is never named), "a tool" (a harness tool). No value, path, header,
  flag, credential or the first build's dotted fallback reaches a label. Visible change: a read chip
  reads "reading a file in the workspace", not the path.
- **The policy input is the first build's (decisions do not move with the chip).** `Action.host` (the
  host a policy rule matches, `archeus/core/policy/rules.py`) is computed exactly as in f483f87 for
  curl and wget (the first positional with a dot or `//`). The chip's host is the separate
  `Action.chip_host` (`archeus/core/domain/actions.py`), never input to policy. The host bug is
  T-143, not this slice.
- **Classifier rules (the complete list, against f483f87).** The block below is the rule as code states
  it (`classifier_rules()` in `canonical.py`). A test (`test_gate_classifier_block_matches_the_code` in
  `tests/v1/integration/test_p21_activity.py`) fails when this block and the code differ. Each rule
  moves a command to a class policy judges more strictly (unclassified, or external_comm for web); none
  moves one to a looser class (checked over 18,772 generated shapes against f483f87, the table below).
  Rules, as they read against f483f87:

<!-- classifier-rules:begin -->
- unclassified: a first word with = (NAME=value); the programs ., alias, at, batch, builtin, busybox, call, cgexec, chronic, chroot, chrt, command, dbus-run-session, declare, doas, env, eval, exec, expect, export, fakeroot, firejail, flock, gdb, ionice, lldb, ltrace, newgrp, nice, nohup, nsenter, parallel, pkexec, proxychains, proxychains4, runas, runuser, screen, script, set, setarch, setsid, sg, socat, source, start, stdbuf, strace, su, sudo, systemd-run, taskset, time, timeout, tmux, torsocks, trap, typeset, unbuffer, unshare, watch, wsl, xargs
- find with -exec, -execdir, -ok or -okdir
- a first word, or a shell or interpreter argument, with an unquoted {, }, *, ? or [
- a shell operator outside quotes: | ; & < > ` ( ) ! and $( , or a newline or a carriage return; a $ or a backtick anywhere
- git: -C, --git-dir, --work-tree, --namespace and --super-prefix are skipped with their value; -c, --config-env, and any other global option not in the tables, make the call unclassified
- a program not in the tables, given an argument that after a directory, a quote, leading dashes or = is one of: base64, brew, busybox, caffeinate, cargo, cat, cgexec, chmod, choco, chronic, chroot, chrt, cp, curl, dbus-run-session, diff, dir, doas, docker, echo, env, expect, fakeroot, file, find, firejail, flock, gdb, gem, gh, git, go, grep, gtimeout, head, helm, hyperfine, ionice, kubectl, less, lldb, ln, ls, ltrace, make, man, mkdir, more, mv, newgrp, nice, nohup, npm, npx, nsenter, numactl, parallel, pip, pip3, pkexec, pnpm, podman, prlimit, proxychains, proxychains4, pwd, rg, rm, rmdir, rsync, runas, runcon, runuser, scp, setarch, setpriv, setsid, sftp, sg, socat, sort, ssh, stat, stdbuf, strace, su, sudo, systemd-run, tail, tar, taskset, terraform, timeout, tmux, torsocks, touch, tree, type, unbuffer, unshare, uv, vercel, wc, wget, which, winget, wsl, xargs, yarn, or a family name (below)
- an option, or a key=value word, whose name is pre, pre-glob, or contains command, exec, pager, editor, shell, eval, hook, helper or program: for any program but git
- less, more, most, pg: an argument starting with + or containing !; man: an argument starting with -P
- a program name is normalised first: a directory, quotes, .exe, .cmd, .bat, .com, .ps1 and a version suffix (python3.11, perl5.36) are dropped
- families (closed): shell: ash, bash, csh, dash, elvish, fish, ksh, mksh, nu, rbash, sash, sh, tcsh, xonsh, zsh; pwsh: pwsh, powershell; cmd; python: py, pypy, python, pythonw, pyw; node: node, nodejs; perl; ruby; php; sed: sed, gsed; code: any name ending awk, and bun, deno, emacs, ex, expect, groovy, gvim, jshell, julia, lua, luajit, nvim, osascript, rscript, rvim, tclsh, vi, view, vim, vimdiff, wish (code is always unclassified)
- anywhere in the arguments: -c, -e or /c as whole words
- shell family: a single-dash word anywhere in the arguments holding one of cCeE (a glued value counts); --command
- python family: a single-dash word holding c; node family: holding e or p; --eval, --print; perl: e or E; ruby: e; php: r, R or B
- sed: an e command (1e rm) or an s///e flag
- cmd: an argument with /c, /k, /r anywhere, in any case
- powershell, pwsh: an argument whose first letter is c or e (a glued value counts: -cRemove-Item), except -ExecutionPolicy and -ConfigurationName in full; the dash may be a hyphen, an en dash, an em dash or a horizontal bar
- git: rebase with -x or --exec; config with a key containing alias, pager, editor, command, helper, hook, external, textconv, fsmonitor, askpass, program: unclassified
- send flags (external_comm, not web): the names -d, -F, -T, --data, --data-raw, --data-binary, --data-urlencode, --data-ascii, --upload-file, --form, --form-string, --json, --post-data, --post-file, --body-data, --body-file; a long flag starting with --data, --form, --post- or --body-; a short -d, -F or -T, attached or not; -X or --request with a method other than GET (as the next word, attached, or with =)
<!-- classifier-rules:end -->

  **Every move against f483f87** (review round 7; `py tools/p21_classifier_moves.py f483f87` prints
  these counts). 327,986 generated shapes (programs x pre-options x payload forms x tails, a newline
  after each program, the curl and wget send forms, git global options, plain commands, and the
  round-7 families and wrappers): 235,702 moved, 0 held-to-allowed. Every move goes to unclassified,
  to external_comm, or to a class policy judges more strictly (`destructive`, `git_push`, `write_repo`):
  6 shapes exec to destructive (`git -C . reset --hard`), 6 to git_push/destructive (`git -C . push
  --force`), and 6 to write_repo (`git -C . add`: the directory was read as the subcommand before, so the
  call was plain exec; the real subcommand is now judged). No shape became allowed. Moves by group, in
  shapes:
  - the launchers, wrappers, builtins and aliases of the table (`wsl`, `runas`, `pkexec`, `fakeroot`,
    `runuser`, `unshare`, `nsenter`, `systemd-run`, `firejail`, `proxychains`, `dbus-run-session`,
    `expect`, `gdb`, `lldb`, `at`, `batch`, `start`, `call`, `ltrace`, `torsocks`, `sg`, `newgrp`,
    `cgexec`, `chronic`, `socat`, `screen`, `tmux`, `setarch`, `doas`, `chroot`, `script`, `parallel`,
    `command`, `builtin`, `alias`, `declare`, `typeset`, `export`, `set`, `trap`, `stdbuf`, `busybox`,
    `ionice`, `setsid`, `chrt`, `taskset`, `flock`, `unbuffer`, `strace`, and the rest of `_NEVER`):
    113,827 to unclassified.
  - the families, each to unclassified: code by nature (awk and its variants, lua, deno, bun, Rscript,
    julia, tclsh, the vi family, emacs): 27,876; shells (sh, bash, dash, ash, ksh, mksh, zsh, csh, tcsh,
    fish, rbash, nu, elvish, xonsh): 24,008; python (python, python3, py, pypy, pythonw, pyw, with
    their versions): 11,504; cmd: 3,681; pwsh and powershell: 3,603; perl: 2,988; php: 2,924; node and
    nodejs: 2,820; ruby: 2,764; sed: 1,324.
  - other programs, held because an argument names a command word or a family (`gtimeout`,
    `prlimit`, `numactl`, `caffeinate`, `setpriv`, `runcon`, `hyperfine`, `docker run`, `rg --pre`,
    `less +!`, `man -P`, `sort --compress-program`, `tar -I`, `npm exec --call`, the brace and glob
    first words): 32,113 in all, with the rest of the shapes of `rm`, `ls`, `cat`, `find`, `make`, `npm`,
    `npx` and `base64` that a newline separates (21 newline shapes, see below).
  - remote tools (`ssh`, `scp`, `rsync`) with a family name among their words (`ssh -o ProxyCommand`,
    `scp -S`, `rsync -e`): 2,364.
  - git: 2,288. The global options before the subcommand are skipped with their value; `-c`,
    `--config-env` and any unknown global option make the call unclassified; `rebase -x` and
    `rebase --exec`, and a `config` key that names a command (alias, pager, editor, command, helper,
    hook, ...) are unclassified.
  - curl and wget send forms, web to external_comm: 232; the curl and wget newline shapes, 4.
  - a subshell and a negation, `(rm -R build)` and `! rm -R build`: operators now (2 shapes).
  - a newline or a carriage return is a separator (`ls\nrm -R build`): unclassified; a newline inside
    quotes is text (`grep "a<newline>b" x` stays a read).
  Not moved, checked by the tool: `npx -c"..."` stays a plain exec (the owner's answer: npx is not in
  the set), `ls *.py`, `cat *.md` and `grep rm file.txt` (reads stay reads, E12), `NODE_ENV=test npm
  test`, `npm run start`, `pytest .`. The owner's Q1 example `NODE_ENV=test npm test` is **not** a move
  against f483f87: f483f87 already held a first word with `=` (its `'=' in argv[0]` test). It is held now,
  as it was then; recorded so the answer is not read as covering a move that did not happen.
  Not in the tool's corpus, covered by tests: a launcher or a command word given to a program outside the
  tables (`mytool bash -c x`, `mytool C:\Windows\System32\cmd.exe /c x`; E15, E18), the argument words that
  must not hold (`npm run start`, `pytest .`; E16), the invented names (E18, E19), and the invariant
  over the launcher table and the corpus (E20).
  - Attached values count as the flag's value: `bash -c"rm -R build"`, `cmd.exe /c"x"`,
    `node --eval=x`, `powershell -ENC"x"` (the shell's quotes are gone when the rule reads the word).
  - Shapes the rules leave alone, by design: `node -r x.js` and `py -E x.py` (not code from the
    arguments), `python -P x.py`, `python -m pytest -q` (the module's own arguments), `node --version`.
  Against 0e63eeb (round 2), the shapes round 2 held and round 4 allows (for example `python app.py -lc`)
  and the shapes it allowed and round 4 holds are both in the review trail; the table above is against
  f483f87 only, which is the baseline the owner accepted.
- **The read.** `GET /v1/executions/{id}` carries it (schema `CurrentAction`, `observe`).
- **The chip (A-17).** `clients/app/src/state/chips.ts`: an `execution.hook` frame re-reads the
  execution; a current action newer than the last one chipped for it, of a live run, becomes a chip on
  its mission's row while a row of it is on screen. Text: the label's words ("reading a file in the
  workspace", "refused: running npm", "held: fetching example.com"); 2.5 s, 4 s when Core refused or
  held the call. A row shows 3 at once. A further chip waits in that row's queue: first in first out,
  6 per row, and beyond 6 the oldest waiting chip is dropped. A frame that arrives while a queue waits
  queues behind it. When a chip leaves, the whole queue is asked about at once (one round of reads,
  each bounded by 2 s), and chips take the room in order, each only if its run is still live; a chip
  whose run ended, or whose read Core does not answer in 2 s, is dropped. A refused or held chip is
  announced when it is accepted (shown or queued), through the app's one polite region (`announce()`
  in `clients/app/src/a11y/announce.ts`); a chip the queue drops later was still said. Residual: that
  region keeps only the latest announcement per 5 s (the app's rule). The chip itself is drawn by
  `ActivityChips` in `clients/app/src/components/ui.tsx` on `MissionRow` (Work and Now; separate routes,
  so one row is never drawn twice), hidden from the row link's name; never a tint. The registry entry
  `activity-chip` is `built` (`tokens/motion.json`), `over_cap` `queue`; under reduced motion the chip
  appears and leaves without its fade.
- **Not built:** the role word and model label the orchestration plan allows on the chip
  ("reviewing · claude-sonnet-5"); TUI chips (the gate's TUI scope is `status` and `doctor`).

**Owner questions.**
- Q1 (answered 2026-10-21: "Accept all three"): the three examples above. Two are moves; the third
  (`NODE_ENV=test npm test`) was already held by f483f87 (see the table).
- Q2 (answered 2026-10-21: "Separate card"): the host bug (`curl -H "X: a.b" https://evil.example/x` has
  policy host `x`). It is T-143, which is not this slice; the policy host here stays the first build's.
- Q3 (answered 2026-10-21: "Q3 accept"): the ellipsis rule for host labels is accepted. Residual,
  recorded: a host label that is only plain letters (for example `zqkwmxtp.example`, or a 20-character
  plain-letter label) still shows, because the rule cannot tell a random plain-letter label from a word.
  The host is already the first build's policy host, so the decision input carries it today; the chip
  adds only its display. E03 and E08 pin the elision (`zq9Kt4mP.example` reads "….example",
  `hunter2.example` and `api.hunter2.example` leak nothing).
- Q4 (answered 2026-10-21: "Q4 keep rule (Recommended)"): the payload rule stays as listed in the block
  above. Not taken: a full inversion (any single-dash flag of a payload-capable tool that the rule does
  not name becomes unclassified), which would hold `python -m pytest -q` and `node --version`. Those two
  stay allowed. A named rule is added for any new shape found.
- Q5 (answered 2026-10-21 by the coordinator's relay: "widening accepted"; npx stays out, the owner's
  answer on npx): the round-5 widenings that go beyond Q4 as answered. (a) The payload scan no longer stops at the first
  positional, because a value option (`bash -o pipefail -c"x"`, `python -X utf8 -c"x"`) hid the code: a
  code letter in any single-dash word now holds, so `node server.js -p 3000` and `python script.py -Ec x`
  hold too. (b) Wrappers added to the unclassified set: `setarch`, `doas`, `chroot`, `script`, `parallel`.
  (c) The operators `(`, `)` and `!` outside quotes. (d) `find` with `-exec`, `-execdir`, `-ok` or
  `-okdir`. (e) A brace or glob (`{ } * ? [`) in a first word, or in an argument of a shell or
  interpreter. Not done: `npx -c"..."` stays a plain exec, since `npx` runs packages by design; the owner
  decides whether it joins the set.
- Q6 (answered 2026-10-21 by the coordinator's relay: "Yes elide, keep 4-char"): the host-label rule
  elides a dotless host, a token-shaped TLD and an all-digit label longer than 6. The 4-character token
  (`a1b2.example`) still shows. The plain-letter residual of Q3 stands.
- Q7 (review round 7, open; the builder's recommendation: keep the plain exec): an unknown program whose
  arguments name no command, family or run option is a plain exec today, the class the first build gave
  it. The reviewer asked for unclassified. Holding every unknown program would hold npm test, pytest, make
  and the rest of the toolchain; the structural rule above holds every program that runs something. Owner
  decision: keep plain exec, or hold all unknown programs.
- Round 6 (review of 804eca0): R7, a newline or a carriage return is a separator (`_OPERATOR` now has
  `\n` and `\r`; a newline inside quotes stays text). R8, git's global options before the subcommand
  are skipped with their value (`_git_split`); `-c`, `--config-env` and an unknown global option make
  the call unclassified, and `_git` passes its unclassified flag on (it was dropped). R9, a launcher or
  wrapper is unclassified: the table `_NEVER` gains `wsl`, `runas`, `pkexec`, `fakeroot`, `runuser`,
  `unshare`, `nsenter`, `systemd-run`, `firejail`, `proxychains`, `proxychains4`, `dbus-run-session`,
  `expect`, `gdb`, `lldb`, `at`, `batch`, `start`, `call`, `ltrace`, `torsocks`, `sg`, `newgrp`,
  `cgexec`, `chronic`, `socat`, `screen`, `tmux`; and structurally, a program not in the tables given
  an argument whose first word is a shell, an interpreter or a launcher (`_LAUNCH_ARG_WORDS`) is
  unclassified. The generic words (`start`, `set`, `.`) stay out of the argument rule, so `npm run start`
  and `pytest .` remain plain exec (E16). S4, a cmd switch glued after another (`cmd /s/c"x"`, `/d/c`)
  holds: any `/c`, `/k` or `/r`, any case.
- Round 7 (review of 025c812). The classifier is structural now, by family and by pattern, not by a
  list of names. (1) A program name is normalised before any lookup (`_norm`): lower case, no
  directory, no quote, no .exe, .cmd, .bat, .com or .ps1, no version suffix (python3.11, perl5.36,
  pypy3). (2) Families (`_family`, a closed set): shell (sh, bash, dash, ash, ksh, mksh, zsh, csh,
  tcsh, fish, rbash, sash, nu, elvish, xonsh); pwsh (pwsh, powershell); cmd; python (python, pythonw,
  pyw, py, pypy); node (node, nodejs); perl; ruby; php; sed (sed, gsed); and code by nature, which is
  always unclassified: any name ending awk, lua, luajit, deno, bun, rscript, julia, tclsh, wish, the
  vi family (vim, vi, nvim, ex, view, rvim, gvim, vimdiff), emacs, expect, groovy, jshell, osascript.
  (3) A program not in the tables is unclassified when one of its arguments, after a directory, a
  quote, leading dashes or `=`, is a family name or a command word of the tables (`_names_command`):
  `gtimeout 5 rm -R build`, `prlimit --nofile=10 rm -R build`, `docker run alpine rm -R /w`, the bare
  Windows path `C:\Windows\System32\cmd.exe /c x`. (4) An option, or a key=value word, whose name is
  pre or pre-glob, or contains command, exec, pager, editor, shell, eval, hook, helper or program, is
  unclassified for any program but git (`_gives_a_command`): `rg --pre`, `ssh -o ProxyCommand=`,
  `sort --compress-program=`, `--exec`, `--editor`. (5) Pagers: less, more, most and pg with an
  argument starting with + or containing !; man with -P. (6) PowerShell's switch prefix is a hyphen, a
  slash, an en dash (U+2013), an em dash (U+2014) or a horizontal bar (U+2015) (`_SWITCH_DASHES`). (7)
  git: rebase with -x or --exec, and config with a key that names a command git runs later (alias,
  pager, editor, command, helper, hook, external, textconv, fsmonitor, askpass, program), are
  unclassified. find -delete stays write_repo (the owner's answer). (8) scp, rsync and ssh: a family
  name among their words is unclassified (`scp -S`, `rsync -e`, `ssh -o`). (9) Argument-carried
  commands (the owner's answer S5, yes): `tar --to-command`, `tar -I`, `tar --use-compress-program`,
  `sort --compress-program`, `rsync --rsh`, `ssh -o ProxyCommand`, `scp -S` are held by the rules above;
  a program named by an option value that is in no family or table runs as a plain exec, as any program
  does (residual, below).
  The invariant is property-tested (E20): for every launcher of the table, and for thirty invented
  program names, in front of each command of a corpus, the result is unclassified, or the same class as
  the command alone. An unknown program with no command argument stays a plain exec (E19): holding every
  unknown program would hold npm test, pytest and make, which the first build allowed; see Q7.
- Not guaranteed (residual, documented): code that is not in argv. The classifier reads argv only:
  `make -f evil.mk`, `npm run <script>` (the script body), `npx <package>` and `pnpm dlx <package>`
  (the package's code), `pwsh -` and `python -` reading stdin, `sed -f script.sed`, `python -m <module>`
  (the module's code), and any file a program reads for its own code.
- Decoy row (review of 025c812, R6; no code change). The E03 expectation row is test_p21_activity.py
  line 120, `curl --proxy-header http://decoy.example https://h.example/x`, expecting ('web', 'curl').
  The planted-secret HOSTILE row that replaced the original decoy HOSTILE row is line 221,
  `curl --proxy-header http://decoy.example/hunter2 https://h.example/x`. The original decoy row was
  replaced, not deleted (owner decision "Replace, don't delete"). Line 211, `curl https://hunter2=x.example/x`,
  is an invalid-host row that stays; line 118 is another E03 row.
- The T-143 policy-host bug (`curl -H "X: a.b" https://evil.example/x` decides on `x`) is NOT fixed here.
