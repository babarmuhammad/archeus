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

Owner amendment (2026-10-25, T-148): P21 also owns the read-only Replay & Recovery read beside Trace, with one vocabulary and derivation in Core and proof mutants in `tools/mutate_p21.py`.

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
- Slice H (T-129): `next_run_at` lives in the automation's body, with no numbered migration for
  the schedule state (§6 expected one); its fires do not bump the row's version (§12 Slice H).

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

### Slice G amended by T-106 (2026-10-21)

"Slice G as built" says the tray says an approval request and an e-stop and nothing else. Since
T-106 (the owner's T-110 answer Q6, "CLI status + mission reason + notification (Recommended)",
2026-10-21) it also says a harness's start breaker opening: for a `harness.state_changed` event
whose payload has `breaker: open`, `gui.notice` returns "<harness> cannot start a process;
Archeus tries again in 5 minutes", the harness named by the event's subject id and nothing else
of the event (its `reason` is never said). The event is appended once per trip, when a closed
breaker opens, never for a failed half-open trial (p20-design-gate item 131). Tested by
`tests/v1/integration/test_spawn_breaker.py` (the notice text from the recorded event); the tray
timer itself is still exercised only through `Shell.notices`.

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
- **S4: the scans.** `own_calls` reads the day's `route_decisions` by `created_at` and parses each
  body in Python to keep the `subject.kind` `archeus_call` rows. No `json_extract` is used: the
  SQLite 3.31 invariant in `test_db_schema.py` holds (owner decision, 2026-10-22). `live_work` and
  `live_counts` each read the live executions by state in SQL (`executions_by_state`, no finished
  execution is decoded); `live_counts` reads each live execution's `account_id` in Python and each
  reads the day's own calls. `/v1/accounts` runs both once: four scans, whatever the account count,
  and each account adds one read of its own usage rows (`ledger_totals`). `refresh_ledgers` (the
  own-call writer) computes `live_counts` once for all its accounts. Ceiling, recorded: the day's
  `route_decisions` are still scanned by `created_at` (no index), and every one of them is parsed
  in Python. An index is a migration; none was added (0019 is not taken), and the owner may ask for one.
- **Field projection on three reads (owner, 2026-10-21: "Field projection only (Recommended)";
  earlier answers "Strip at read" and "Strip it").** Slice B guarantees only this: `/v1/accounts`,
  `/v1/route-decisions` (list and one) and `/v1/status` no longer carry the fields that name an
  account's home, for registered accounts. A default account's key (`<harness>:<canonical home>`) in a
  route decision's `outcome.account_ref` is still returned on the list (`GET /v1/route-decisions`),
  on the single-decision read (`GET /v1/route-decisions/{id}`) and on the mission trace; that is not covered by slice B and is
  deferred to T-144 (see *Not guaranteed* below). Those fields are left out by name, never by matching a value:
  - `/v1/accounts`: `home_ref` and `home_key` (`resources.HOME_FIELDS`).
  - `/v1/route-decisions` (`queries._public_decision`, `get_route_decision`'s usage rows): a snapshot
    account's `ref`, `home_ref` and `home_key`; `account_ref` on the decision, on each candidate and
    on each usage row.
  - `/v1/status`: an own call's `account_ref` (`live.live_work`).
  The stored rows keep every field (the execution manager reads the snapshot). The mission trace
  (`/v1/missions/{id}/trace`) reads its `route_decisions` through the same `queries.route_decisions`,
  so the same fields are left out there (review N-1). That is what the code does, not a wider
  guarantee: the trace's other fields are not projected by slice B. Tests:
  `test_owner_2026_10_21_the_accounts_view_never_shows_an_account_home`,
  `test_owner_2026_10_21_route_decision_reads_name_no_home_field`,
  `test_owner_2026_10_21_the_default_account_fields_are_left_out`,
  `test_owner_2026_10_21_live_work_names_no_home_field`,
  `test_owner_2026_10_21_the_mission_trace_reads_no_home_field` (the trace; mutant Z202), and
  `test_H09_the_three_projected_reads_name_no_home_field` (HTTP, with a stored-row precondition).
  `test_H09_the_status_read_with_a_live_own_call_names_no_home_field` (HTTP: the status read with an
  own call in flight, so the own-call projection runs over HTTP and not only on `live_work`; review
  N-2; mutant Z203). Mutants Z151, Z153-Z157, Z202, Z203.
  **Not guaranteed by slice B (moved to T-144, the security card):** every other read that can carry
  a home. Known examples: verification and review records (`performed_by.account_ref`,
  `reviewer_resource`), events payloads, a default account's key (`<harness>:<canonical home>`,
  ADR-0048 D-25.1) in a route decision's `outcome.account_ref` (the own-call writers in
  conversation, knowledge and planning record it there; the decision's `account_ref`, its
  candidates and its usage rows are projected, and a default account has no `account_id` on any
  of them), any
  free text that names a home, and the event streams. A value-matching net was built and removed
  on the owner's answer; its spelling and boundary findings are on the T-144 card.
- **Now map (review F2).** The live map's set is `attemptIds(status.data.live)` (`orbit.ts`): an own
  call is never a map node (G8). Test: `orbit.test.ts` (`attemptIds`, behaviour only); mutant Z148.
  The offline header is `headerLine(status)` (`present.ts`), tested in `present.test.ts`; mutant
  Z150. The source-text pins are gone; the map and the header are pure functions now.
- **S5: mutant gaps.** Z130-Z142 cover the in-flight count, its account (Z131 books it to no
  account), the lapsed flip, the in-flight zero, the palette skip, the TS and Python in-flight
  text, the TUI usage line, the execution-only link filter, the summary-only consumers, the
  "(+N more)" count and the own-call kind filter. The account filter inside `live_counts` for a
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

### Slice H as built (2026-10-21, card T-129; rework after review, same card)

Built under D9 "Build in P21" and the owner's 2026-10-21 naming of slice H under D0 ("Yes, all
five (Recommended)", recorded on the board's "Owner 2026-10-21" block and appended to D0 at
integration). It changes no routing behaviour: a schedule only asks for a mission, through P14.
The owner's answer on missed times (2026-10-21): "Once together (Recommended)", as built.

- **The trigger.** `{kind: 'schedule', every}` beside P14's `{kind: 'event', type, where}`
  (`archeus/core/automation/matcher.py` `validate_trigger`, `every_s`, `next_due`; the matcher stays
  pure). `every` is the legacy loops' interval grammar (`claude_sessions/loops.py`
  `_interval_minutes`: `15m`, `2h`, `1d`, a bare number is minutes), stored normalised (`' 2 h '`
  is `2h`). The period is at least one minute and at most 7 days (the loops' cap, loops.py:292),
  and the digits are bounded to six, so an overflowing period is refused when written, never
  when enabled. Seconds are exact here (the loops floor them to whole minutes; no loop uses them).
  Condition triggers stay unbuilt (p14 D14). An event never matches a schedule trigger, and the
  due event is an `automation.*` type, which no event trigger may name (p14 D10).
- **`next_run_at`: a field of the automation's body, deliberately not a migration.** Deviation,
  declared here (§11). The cost is that the field lives on the versioned row, so the fire moves
  the row without bumping its `version` (`writer.update(..., bump=False)`): a person's
  `expected_version`, read before a fire, still works. The API reports `next_run_at` only while
  the automation is ENABLED (`automations._view`); a disabled or suspended schedule reports null.
- **Claim-and-advance (ADR-0020, state-machines §8).** `automations.fire_due(automation_id)`, ONE
  writer command per due schedule: the due check is made inside the transaction, the time moves
  to the first point on its grid after now, `automation.schedule_due` is appended (payload:
  `due_at`, `every`, `next_run_at`, `missed`), and the run is claimed through P14's `_claim`, so
  the depth, rate-limit, loop-guard, e-stop and execution-actor guards apply as to an event. A time
  is claimed once: a second pass, a second worker or a restart finds it already moved on.
  **Missed times (owner, 2026-10-21): once together.** The times a stopped Core missed fire as one
  run; `missed` on the rationale and the event says how many grid points were skipped.
- **A schedule that may not run is not claimed.** Its project gone or archived, or Core disarmed
  (e-stop): the time stays due and fires once together when it may run again. Claiming it anyway
  wrote a denied or condition_false run every period, and neither reason counts toward the loop
  guard. The API says why in `waiting` ("project gone or archived", "Core disarmed"), null
  otherwise, and a waiting schedule is not in Upcoming.
- **Faults are per schedule.** The worker (`worker.py` `_fire_due`) runs one command per due
  schedule. A claim that raises is held and retried with backoff like an event, then quarantined
  for this process after `MAX_ATTEMPTS` (a restart retries it). Other schedules still fire. The
  API's `waiting` carries the recorded cause ("quarantined after 3 failures: <error>", the error
  flattened to one line and capped at 200 characters; an event quarantine's cause is capped the
  same way), so Upcoming drops the schedule and Control shows it as Waiting. Re-enable does not clear the quarantine
  (deferred, r1 N6: it lasts until restart).
- **A due time in the future.** `waiting` is read whenever a time is set, so a schedule whose gate
  holds it now shows the reason before its time comes; it is held when due, and fires then.
- **When it runs.** The worker checks for due schedules at the start of every pass, which runs on
  every commit and at least every `WORLD_POLL_S` (10 s), so a time fires at most that late.
- **Simulation.** `simulate` on a schedule answers how many times it would have come due had it
  run for the whole window (`scheduled`), not events.
- **Seen.** SPA: Control shows "Every 15 minutes" and, while enabled, "Next run in 12 min";
  Now's Upcoming adds the enabled schedules that are not waiting, soonest first, after the approved
  and planning missions (`now.ts` `scheduled`, `Now.tsx`); Control shows "Waiting" with the reason
  in place of "Next run". A run's "why" says "It fired on its schedule, every day". TUI: Control
  shows "Waiting" or "Next run". The offline Now snapshot does not keep the automations
  read, so it shows no schedule. Times are UTC periods from the enable instant, not wall-clock.
- **Tests:** `tests/v1/integration/test_schedule_triggers.py` (H01 fires at its time and not
  before, once; H02 a restart fires four missed times once, `missed` 3, and keeps the grid; H03 two
  workers on one time claim it once, and a claim made after that commit finds the time moved on
  (forced, not raced); H04 the loop guard suspends a schedule and the API reports no
  time; H05 a disabled schedule does not fire, reports no time, and re-enabling restarts its clock;
  H06 events and schedules never cross; H07 over HTTP: `next_run_at`, the simulation, the one-minute
  floor; H08 a mission a schedule asked for starts a rule one level deeper; H09 a fire does not
  bump the version; H10 an archived project or a disarmed Core waits, says why in `waiting`, and
  fires once; H11 a claim that raises holds only its schedule, then quarantines it and says why in
  `waiting`); `tests/v1/unit/test_automation_units.py` (the grammar and its 7-day cap, the refusals,
  `next_due`, no match); `clients/app/test/now.test.ts` (a held schedule is not upcoming; Control's
  row says why, else the next run); `tests/v1/tui/test_acceptance.py` (a held schedule's Control row
  reads Waiting with the reason and no Next run).
- **Mutants:** Z100-Z109 and Z400-Z410 in `tools/mutate_p21.py`, each killed by a test it names
  (Z400 the 7-day cap, Z401 the digit bound, Z402 the in-transaction due check, Z403 the loop
  guard, Z404 the API's null time, Z405 the version bump, Z406 the archived or disarmed skip, Z407
  the per-schedule isolation, Z408 the quarantine, Z409 the simulation count, Z410 the missed count);
  Z411 the API's `waiting` reason, Z412 a held schedule listed as upcoming, Z233 Control's row
  drops the reason (`scheduleRows`), Z234 the TUI row drops the reason, Z235 the worker keeps no
  cause for a quarantine, Z236 the view drops the quarantine.

### Slice C-write as built (2026-10-21, card T-126)

The owner's word that line 180 asks for, 2026-10-21 (AskUserQuestion, verbatim): "Build P21's
remaining pieces today (B live activity/usage, E what an agent is doing now, H scheduled work,
Health page + attention, C-write cause of each action) instead of waiting for P20?" = "Yes, all
five (Recommended)". D13 (b) as approved; "P21 cannot be declared complete before P20 is" stands.

- **One place, not every call.** The writer's transaction carries a `cause`: an event appended
  without a `cause_chain` of its own gets it (`archeus/infra/db/writer.py`, `Tx.append`); an
  explicit cause still wins (the automation consumer's chains, `create_mission(cause=)`). A command
  takes its cause from `events.CAUSE`, a context variable that `Writer.submit` reads on the
  submitting thread and queues beside the arguments, never inside them: the idempotency request
  hash, `PROOF_ARGS` and the token rows are unchanged, and a keyed retry under another cause is a
  replay, not a conflict.
- **Issued from an event.** `consumers.deliver` sets `CAUSE` to the event's chain plus its id
  (`events.caused_by`: the newest 16, the automation consumer's own rule, which now calls it) while
  the handler runs, and resets it afterwards, a `Hold` included. Everything the intent, planning,
  knowledge and automation consumers write carries the event that triggered it, their own calls'
  route records and ends (`core/calls.py`) included, with no edit to `core/calls.py`,
  `resources.py`, `commands.py` or `conversation.py`.
- **Issued from an approval.** In `authorization.py`, once the approval's own decision event is
  written (`decide`'s reject and request-changes path, `_approve`, `_approve_route`), `tx.cause`
  becomes that event's chain plus its id, so the plan, task and mission moves the decision issues
  carry it. The decision event itself is the user's command: a root (or, decided under a consumer,
  that consumer's event). Three assignments, each after every check: the re-judging, the guards,
  the step-up check and every refusal run before them and are unchanged, and a refused decision
  still writes nothing.
- **Roots, by (b)'s wording.** A route's command (a direct user command), the engine and execution
  loops (they poll rows), the verification worker, policy expiry and the world worker.
- **The reply to an execution ending (addition, owner 2026-10-21).** Asked whether the task's
  response to an execution ending (in the transaction that appends `execution.ended`, so not
  issued from an event by (b)'s wording) should be caused by `execution.ended`, the owner answered
  (AskUserQuestion, verbatim): "Yes, link it (Recommended)". Built in `executions.py`: each of the
  four writers of `execution.ended` (`refuse`, `_ended`, `record_handoff`, `approval_answered`)
  keeps the event it appends and runs what follows (the task's retry, verification or failure, a
  refusal's mission block, a hand-off's continuation) inside `_after(tx, ended)`, which sets
  `tx.cause` to that event's chain plus its id and restores the previous cause on the way out, so
  one command that ends several executions (an e-stop, a mission stop) gives each reply its own
  end and leaves its own later events (`core.estopped`) unaffected. An INTENT refused before it
  spawned writes no `execution.ended`; its reply stays a root. The hook-token clearing on those
  paths is unchanged (the same `hook_token_hash: None` fields in the same edges), and a test
  asserts the token is gone after the end.
- **Deviation from the file-scope note.** `.collab/T-119-cwrite-scope.md` passed `cause` as an
  argument through every issuing call (twelve modules, credential- and auth-bearing ones among
  them) and rejected a writer default for touching `writer.py`. Built instead: the writer default,
  a few lines in `writer.py` away from its hash, proof and token code, so no issuing call can be
  missed and only `authorization.py` among the excluded files is edited (three lines), under the
  owner's word.
- **Decision scope (review of b0bc245, Required 1).** `decide` is wrapped by `_restores_cause`
  (`authorization.py`): the cause the three assignments set ends when the decision returns, so the
  command that called it keeps its own cause. Before, a chat approve's reply (`decide_by_message`,
  `conversation.py`) was written caused by the decision; that reply is the route command's, a root.
  The decision's arguments, guards and outcomes are unchanged.
- **Files as built.** `archeus/infra/db/writer.py` (`Tx.__init__`, `Tx.append`, `Writer.submit`,
  `Writer._run`, `Writer._one`; not `request_hash`, `PROOF_ARGS`, the idempotency table or the
  token methods), `archeus/core/domain/events.py` (`CAUSE`, `caused_by`), `archeus/infra/eventlog/
  consumers.py` (`deliver`), `archeus/core/application/authorization.py` (`_restores_cause`, the
  three assignments, the `functools` import), `archeus/core/application/automations.py` (`_claim`),
  `archeus/core/application/executions.py` (`_after` and its four call sites). Nothing else under
  `archeus/`. Stated on the record because the scope note flagged `writer.py`.
- **Recorded from the review, not changed.** Own-call ends of `core/calls.py` (no harness, emergency
  stop, provider terms, adapter error, invalid answer) run on a consumer thread and now carry its
  cause; that is (b)'s rule, reached without editing `calls.py`. `approval_answered` is called from
  the manager's poll loop, a root, so the task's reply is caused by its `execution.ended` and not by
  the approval decision (no link from approval to reply; the owner's rule for the reply, unchanged).
  A human verification decision (`verification.py` `Decisions.decide`) is not an approval and
  causes nothing, as (b) says.
- **Display.** Nothing new: the trace (C-read), the timeline and the TUI already show a
  `cause_chain`; more events now have one.
- **Tests:** `tests/v1/integration/test_cwrite.py` (25). The original thirteen: a command under a
  cause, an explicit cause winning and a route command a root; the cause outside the request hash;
  the newest 16 kept; a consumer's writes caused and nothing left behind, a `Hold` included; the
  intent consumer's mission and reply caused by the user's message; plan approve, reject and
  request changes, each deciding as before and causing everything it moved; a decision under an
  event passing it on; a fallback route's approve and reject; a refused decision writing nothing
  (a rollback check, GuardFailed). The addition: an ok and an error end each caused into the task's
  reply with the hook token cleared, and one command ending two executions keeping each reply to its
  own end. Fix round: a chat approve's reply a root while its moves carry the decision; a consumer
  handler that raises leaves no cause behind; each other end site (a mission stop over two paused
  executions, an estop with a paused one, a rejected action approval, a refused hand-off, a
  continuation) caused by its own end, with the mission block and `core.estopped` after an end a
  root. Round 3: a blocking refusal (`path_too_long`) blocks its mission under its end; a decision
  made inside a consumer is caused by that event, and so is its reply.
- **Mutants:** Z70-Z79 (the writer, the consumer, the event chain and the decision's assignments)
  and Z110-Z111 (the `_after` body). For the review: Z170-Z173, one per `_after` site (refuse,
  record_handoff, approval_answered, `_ended`); Z174 (the decision's restore removed); Z175 (a
  blocking refusal's mission block uncaused); Z176 (deliver's reset removed when a handler raises);
  Z180 (the writer ignores the cause it was given). All in `tools/mutate_p21.py`, each killed by a
  test it names. The ids are Z170-Z176 and Z180, not the review's Z112-Z115: T-128 owns
  Z112-Z122 on p21-e, and the two would collide at integration.
### Slice E strict allow-list (2026-10-25; historical rounds retained below)

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
- **The policy input narrows only.** MATCHED means an exact row, not permission: normal P9
  authorization, locked floors and task-contract exclusions still decide. A14/A15 remain `exec`.
  Structured Read/Edit/Grep/WebFetch policy behavior stays unchanged. `Action.chip_host` remains
  display-only. HELD risk labels use closed exact program/subcommand tables, without legacy
  parsing or inferred paths/hosts. Their approval identity binds the raw command. Unknown names
  remain unclassified `exec`. Remote-capable commands are HELD with policy host `None`.
  No MATCHED row bears a URL. Owner decision 2026-10-25: "Defer, doc and pin only (Recommended)".
  [T-143-proposal.md](../../../Archeus/.collab/T-143-proposal.md) (curl/wget) and
  [T-155-proposal.md](../../../Archeus/.collab/T-155-proposal.md)
  (ssh/scp/sftp/rsync/git remote forms) are deferred as preconditions of any future URL or remote
  allow row; no host-derivation code is built now.
- **Strict command allow-list (owner 2026-10-23).** Only the following literal data is eligible.
  This block is generated by `tools/p21_allowlist_gate.py` from `command_allowlist.ROWS`.
  `tests/v1/unit/test_p21_proof_tools.py::test_gate_allowlist_block_matches_data` checks exact
  parity; `test_gate_drift_is_rejected_in_both_directions` checks data and document drift.

<!-- command-allowlist:begin -->
<!-- GENERATED from archeus/core/execution/command_allowlist.py ROWS. Do not hand-edit. -->

| ID | Program | Fixed prefix (exact, in order) | Complete option vectors (exactly one, before the operands) | Operands | Class |
|---|---|---|---|---|---|
| A01 | pwd | — | (no options) | none | read |
| A02 | ls | — | (no options) · `-l` · `-a` · `-a -l` | `P*` | read |
| A03 | cat | — | (no options) | `F+` | read |
| A04 | head | — | (no options) · `-n 20` | `F+` | read |
| A05 | tail | — | (no options) · `-n 20` | `F+` | read |
| A06 | wc | — | (no options) · `-l` · `-c` · `-w` | `F+` | read |
| A07 | rg | — | `--no-config --fixed-strings` · `--no-config --fixed-strings --line-number` | `search` (literal `--`, then `L`, then `P+`) | read |
| A08 | git | `--no-pager status` | (no options) · `--short` · `--porcelain=v1` | none | read |
| A09 | git | `--no-pager diff` | `--no-ext-diff --no-textconv` · `--no-ext-diff --no-textconv --stat` · `--no-ext-diff --no-textconv --cached` | `optional_paths` (none, or `--` then `P+`) | read |
| A10 | git | `--no-pager log` | `--max-count=20` · `--max-count=20 --oneline` | `optional_head` (none, or `HEAD`) | read |
| A11 | git | `--no-pager show` | `--no-ext-diff --no-textconv` | `head` (`HEAD` only) | read |
| A12 | git | `--no-pager ls-files` | (no options) | `optional_paths` (none, or `--` then `P+`) | read |
| A13 | git | `--no-pager rev-parse` | `--show-toplevel` · `--is-inside-work-tree` | none | read |
| A14 | pytest | — | (no options) · `-q` | `P*` | **exec** |
| A15 | python | `-m pytest` | (no options) · `-q` | `P*` | **exec** |
| A16 | node | — | `--version` | none | **exec** |
<!-- command-allowlist:end -->

  Each vector is complete and ordered, before operands: no aliases, subsets, permutations,
  duplicate switches, abbreviations, attached values, clusters or ignored extra tokens.
  `P*` means zero or more contained workspace paths; `F+` means one or more regular files,
  never stdin `-`. `L` is nonempty ASCII letters/digits/spaces/dot/underscore/hyphen, never
  starting with hyphen; it is literal text, not regex. `HEAD` is the only admitted revision.
- **One scanner, no shell expansion.** `command_allowlist.py` rejects non-string/empty input
  and input above `MAX_INPUT_LENGTH = 131072` before token allocation. A forward pass rejects
  CR/LF/NUL/DEL, ASCII controls except tab, and all non-ASCII. Dollar, backtick, backslash,
  braces (even empty or quoted), globs, tilde, percent and exclamation are forbidden anywhere;
  `| ; & < > ( ) #` are forbidden outside quotes. Space/tab separate tokens outside quotes.
  Only whole single/double-quoted operands are admitted: no escaping, concatenation, embedded,
  empty or unclosed quotes. Program, prefix and options must be wholly unquoted.
  No assignment/env prefix, wrapper, launcher, interpreter family or unknown program is a row.
  No suffix/version/path/case normalization: `.exe`, `.cmd`, `.bat`, `.com`, `.ps1`, `python3`,
  `py`, uppercase programs, quoted executables, `/bin/ls`, `./ls` and Windows paths are HELD.
  No Windows shell row exists; a Bash tool name alone does not attest POSIX execution.
  Paths reject absolute/drive/UNC/ADS/URI/response-file/pathspec syntax, leading hyphen or space,
  trailing space/slash, empty segments and `..`. `.`/`./` designate authenticated cwd.
  Search pattern and option values never become paths. Scanner/matcher storage and work are
  linear in input length; filesystem evidence is separate I/O, not part of this bound.
- **Context prerequisites are evidence, never spelling.** Every row needs trusted POSIX shell,
  program resolution and startup environment. Git additionally needs profile G: trusted binary,
  no alias/function override, pager, external diff/textconv/fsmonitor, hostile config includes or
  environment-selected config/executables. `--no-pager` alone proves none of these. PATH,
  NODE_OPTIONS, Python startup/import controls, RIPGREP_CONFIG_PATH and shell startup files must
  be controlled. Typed paths require contained regular-file/directory evidence; directories need
  descendant containment, including implicit `.` for operand-free `ls`. Lexical checks cannot
  solve symlink/junction escapes, mounts, races or TOCTOU. Missing/unknown evidence means HELD.
  A14/A15 without operands currently require no explicit cwd path evidence; review remains open.
- **Production Bash auto-allows nothing until a node attests the POSIX profile.** Re-grounded on
  this tree: `canonical.py:249` dispatches `canonicalise_hook`, classification is at :253, row
  construction at :271-:279. `manager.py:518` handles hooks, checks cwd at :536, builds context
  at :539-:542, asks node at :543-:544, canonicalises at :545-:546 and forwards eligibility at
  :547-:551; exceptions halt at :552-:554. `local.py:151-:153` returns `None` because current
  isolation does not attest resolution/startup environment. No production profile is enabled.
- **HELD caps automatic allow.** `executions.py:765` authenticates/state/sequence checks before
  authorization; DENY at :812-:813 and ASK at :814-:817 remain in force. Bash cap at :818-:822
  halts otherwise automatic ALLOW with fixed reason `command form needs review` and fixed
  exec/command label. A permissive policy cannot admit a table miss. Explicit approval-backed
  ALLOW remains a separate, exact single-use path (:797, :803, :820), never table membership.
  Structured tools do not enter this cap. `_current` (:859), `_label` (:867) and `_hook_answer`
  (:889-:899) retain closed labels and same-transaction current_action/hook_seq/event writes.
  The old classifier is not an eligibility fallback: `canonicalise_hook` preserves risk classes
  through closed exact program/subcommand tables after strict scan, with no policy host. This path
  remains; it cannot open automatic allow. Offline proof imports baseline versions only in child
  processes. No new live legacy fallback or intersection guard is introduced.
- **No URL or remote rows.** No curl/wget/ssh/scp/sftp/rsync or git remote forms. Later rows must
  await T-143 (curl/wget) or T-155 (ssh/scp/sftp/rsync/git remote forms), derive
  policy host from exact validated destination operands, and define redirects/proxies/multiple
  destinations where applicable.
  Header/value decoys and chip redaction must never supply policy host. The HELD hook path does
  not use first-build host extraction: policy host is `None`, including unclassified git pull
  and git remote add. `test_held_remote_commands_have_no_policy_host` pins eligibility and host;
  `test_each_near_miss_holds_with_allow_all_classes_policy` separately pins the execution cap.
- **User cost and explicit scope.** Everything outside table is HELD: writes/deploy/install/push,
  remote operations, sed/tar/pagers/find, npm/make/ruff, unknown tools, most Git forms, `-la`,
  read globs, quoted newlines and ordinary rg regex. More interruptions and reformulations are
  intentional. False HELD costs time: D6 persists after run end, held/refused chips last longer
  and are announced. No claim that every hold is a one-click approval. A14/A15 execute arbitrary
  workspace tests/conftest/plugins/imports and write caches; `exec` policy and isolation remain
  mandatory. Exact argv proves neither harmlessness nor restricted network use. Descendant
  traversal, trusted-profile limits, code/config effects and TOCTOU remain acknowledged.
- **Both-baseline proof: NOT RUN, gate pending.** `tools/p21_classifier_moves.py` requires archives
  of **f483f87 and 61dc68f**, including tests. It freezes one corpus/context, enumerates every
  option vector and operand cardinality, adds old test literals/static string expressions,
  review snippets and new near-misses, and supplies contained path fixtures plus synthetic
  trusted profile. Legacy classifiers run only in offline child processes. Exceptions, unavailable
  archives, timeouts and missing results fail proof. Reports include class sets, row IDs, HELD cap,
  all-allow/restrictive read+exec/locked-floor/task-contract policies. Both comparisons must exit
  zero with **held-to-allowed = 0**, no DENY/ASK-to-auto-allow and no miss-to-auto-allow.
  No zero count is claimed. Dynamically constructed old test inputs still need corpus audit;
  literal extraction alone does not prove every parametrized/generated input is included.
  See `.pv20-out/E-slice3-final.md` for exact locked commands and outstanding validation.

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
- Q2 (answered 2026-10-21: "Separate card"): the legacy parser's host bug
  (`curl -H "X: a.b" https://evil.example/x` has policy host `x`) remains pinned by E10 through
  `canonicalise`, not the live hook. The hook holds this command with policy host `None`.
  The 2026-10-25 decision defers T-143 and T-155 until a future URL or remote allow row.
- Q3 (answered 2026-10-21: "Q3 accept"): the ellipsis rule for host labels is accepted. Residual,
  recorded: a host label that is only plain letters (for example `zqkwmxtp.example`, or a 20-character
  plain-letter label) still shows, because the rule cannot tell a random plain-letter label from a word.
  Structured WebFetch retains its policy host; HELD remote commands have policy host `None`.
  Chip elision is display-only. E03 and E08 pin the elision (`zq9Kt4mP.example` reads "….example",
  `hunter2.example` and `api.hunter2.example` leak nothing).
- Q4 (historical, superseded for eligibility; answered 2026-10-21: "Q4 keep rule (Recommended)"): the payload rule stays as listed in the block
  above. Not taken: a full inversion (any single-dash flag of a payload-capable tool that the rule does
  not name becomes unclassified), which would hold `python -m pytest -q` and `node --version`. Those two
  stay allowed. A named rule is added for any new shape found.
- Q5 (historical, superseded for eligibility; answered 2026-10-21 by the coordinator's relay: "widening accepted"; npx stays out, the owner's
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
- Q7 (historical; closed by strict allow-list decision 2026-10-23; the builder's recommendation: keep the plain exec): an unknown program whose
  arguments name no command, family or run option is a plain exec today, the class the first build gave
  it. The reviewer asked for unclassified. Holding every unknown program would hold npm test, pytest, make
  and the rest of the toolchain; the structural rule above holds every program that runs something. Owner
  Decision now closed: unknown programs are HELD; only A14/A15 retain test-runner exec forms.
**Historical rounds below are superseded for Bash eligibility by the strict allow-list above.**

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
  unclassified. find -delete is destructive, and find -exec, -execdir, -ok or -okdir running rm is
  destructive (the owner's answer, round 8); any other program after one of them is unclassified. (8)
  scp, rsync and ssh: a family name among their words is unclassified (`scp -S`, `rsync -e`, `ssh -o`).
  (9) Argument-carried commands (the owner's answer S5, yes): `tar --to-command`, `tar -I`,
  `tar --use-compress-program`, `sort --compress-program`, `rsync --rsh`, `ssh -o ProxyCommand`, `scp -S`
  are held. The carrier options `tar -I`, `rsync -e` and `--rsh`, `scp -S` are held whatever the value
  names (round 8, `_CARRIERS`). A program named by any other option value that is in no family or table
  runs as a plain exec, as any program does (residual, below).
- Round 8 (review of 64d5bd9, T-128). (1) find: see round 7, item (7). (2) A wrapper's words are read as argv gives
  them, quotes removed (`gtimeout 5 r""m -R build`, `docker run alpine r""m -R /w`), and a brace or glob
  word that may expand to a command word is held (`gtimeout 5 {rm,-R,build}`, `gtimeout 5 r? -R build`,
  `docker run alpine {sh,-c,x}`): (round 10: every brace word is held as written, see round 10) and a glob matches the command names by its
  pattern (`tests/*.py` stays plain, `tests/*` is held: an over-hold). (3) `rg --pr""e` is read as
  `--pre`: the option rule reads argv too. (4) The carriers of (9). (5) `node --import`, `--loader` and
  `--experimental-loader` with a data: URL is held (the module text is in argv); a module file named by
  these flags, and `node -r`, stay a plain exec (residual, below). (6) git config keys for a filter
  (clean, smudge, process), a merge driver (driver) and core.gitProxy are unclassified. (7) git push is
  destructive with a single-dash word holding f or d (`-fu`), or a `+` before a ref (`+main`), as with
  --force. Owner questions for this round: whether `tar -I` and the other carriers should hold every value
  (as built) or only a value that names a program outside the tables; and whether the store-pin scan
  (test_repo_store) should stay as it is, with the `--git-dir` literal in canonical.py built from parts,
  or take a reviewed exemption for the classifier.
  The invariant is property-tested (E20): for every launcher of the table, and for thirty invented
  program names, in front of each command of a corpus, the result is unclassified, or the same class as
  the command alone. An unknown program with no command argument stays a plain exec (E19): holding every
  unknown program would hold npm test, pytest and make, which the first build allowed; see Q7.
- Round 10 (review of 8e9d77a, T-128; owner decision 2026-10-23, "Fail-closed round 10": whatever the
  classifier cannot fully expand or recognise is held, never allowed). (1) An unquoted brace word with
  something inside (`{a,b}`, `{1..3}`, `{apply}`, a nested `{x,{}}`) anywhere in a command is unclassified,
  for every program: `rm {-R,build}`, `git push {--force,origin,main}`, `terraform {apply}`, `find .
  {-delete}`, `tar {-I,mytool}`. `{}` alone (find's) is not one; a quoted or backslashed brace is text. The
  round-9 `_expansions` (a full cross product, exponential in the pairs: 20 pairs took minutes inside the
  manager's hook pass) is gone, so no bound is needed: the brace word is held as written, in time that does
  not depend on the pairs (E27 holds 300 pairs in under a second). (2) A long option of a carrier (tar,
  gtar, bsdtar, rsync, wget) and of git clone, fetch, pull, ls-remote and push (`--config`,
  `--config-env`, `--upload-pack`, `--receive-pack`, and `--exec`, the alias of the last two) is held under
  any abbreviation of two letters or more, as getopt_long and git's parse-options accept one; so is git
  push `--force`, `--delete`, `--mirror` (destructive) and git rebase `--exec`. `--checkpoint` is an option
  of its own and stays plain. Added by name: tar `--to-command`, `--rsh-command`, wget `--execute`,
  `--use-askpass`, rg `--hostname-bin`, git clone `-u` (any single-dash letter run holding u). (3) tar's old
  style: a first word with no dash that holds I or F (`tar cIf mytool a.tar b`). (4) ssh, scp, sftp `-o`,
  alone, in a cluster or glued, whose value starts with Match or a word naming a command, ended by a blank or
  `=` (`-o "ProxyCommand mytool"`); sftp `-S` is a carrier like scp's. (5) sed: the `s///e` backreference
  names the delimiter (it was group 2, so only `/` was caught), and a script glued to `-e` or
  `--expression=` is read. (6) The cheap Shoulds: `.cmd`, `.bat`, `.com`, `.ps1` are dropped for the tables
  (`npm.cmd publish` is a deploy); gtar and bsdtar are command words; php `-E`, `--run`, `--process-*`; the
  pager and man test reads the program name; git config keys `protocol` and `insteadof`, and an `ext::`
  word, are held. Moves against 8e9d77a (the tool run with it as the baseline): 1,369 shapes, every one
  to unclassified (from read, write_repo, external_comm, web, destructive or plain exec), 0 held-to-allowed.
  Over-holds this round brings: any brace word (`ls {a,b}`), any two-letter prefix of a held name
  (`tar --ne`, `git clone --co`), a clone letter run holding u (`-bmenu`), a tar first word holding I or F,
  an ssh `-o` value whose first word holds a command word.
- Decoy row (review of 025c812, R6; no code change). The E03 expectation row is test_p21_activity.py
  line 120, `curl --proxy-header http://decoy.example https://h.example/x`, expecting ('web', 'curl').
  The planted-secret HOSTILE row that replaced the original decoy HOSTILE row is line 221,
  `curl --proxy-header http://decoy.example/hunter2 https://h.example/x`. The original decoy row was
  replaced, not deleted (owner decision "Replace, don't delete"). Line 211, `curl https://hunter2=x.example/x`,
  is an invalid-host row that stays; line 118 is another E03 row.
- The legacy T-143 policy-host bug remains in `command()` and is pinned by E10. The live hook
  does not call that parser for HELD commands: remote commands have policy host `None` and
  are not `Allowed`. T-143 and T-155 host derivation is deferred until a future URL or remote row.
