# Archeus V1 — Testing Strategy

Status: **DECIDED**. Methodology follows the Anthropic code-migration kit's rule: **no judge, no
exit condition** — the acceptance judge is written before the code it judges (P1), runs against
the public surface (API + event stream), and never imports internals, so it survives every
refactor. It also carries this repository's rules: a gate nobody has watched fail is not a gate
(mutation-verify), and any tool whose output is "passed" needs a floor on how much it checked.

## 1. Test layers

| Layer | Location | What | Runs |
|---|---|---|---|
| Unit | `tests/v1/unit/` | pure functions: state tables, guards, policy evaluation, router ordering, context scoring, grammar, digest grouping, canonicalisation of actions | every commit, < 30 s |
| Property | `tests/v1/unit/` (stdlib `random` with fixed seeds; no Hypothesis dependency) | router invariants, policy precedence, DAG validation, approval hash binding | every commit |
| Integration | `tests/v1/integration/` | writer + outbox + consumers on a temp SQLite; migrations; boot reconciliation with real child processes; SSE replay | every commit |
| Contract | `tests/v1/contract/` | harness adapters against recorded streams (fixtures) **and**, opt-in (`-m real_harness`), against the real CLI with a sandbox account; API route table ↔ generated client ↔ docs | fixtures every commit; real weekly/manual |
| Judge (acceptance) | `tests/v1/judge/` | the scenarios of §2 end-to-end through `CoreClient` (§1.1: in-process until P3.5, then HTTP + SSE) against a Core using the **fake harness** and fake usage/clock | every commit |
| E2E UI | `tests/v1/e2e/` (Playwright, as `tools/smoke_gui.py` today) | SPA flows against the judge's Core fixture: every destination, inspector tab, approval flow; overflow/dead-space audit; animation loop parks. *As built (P18):* `test_spa_p18.py` — the graph drill, keyboard, loop parking (hidden page, lost context, reduced motion), import graph, 390 px fallback with no sideways scroll, focus back to the canvas, a pin never stored, world counts and route facts, hover, search centring, "no path", Esc, touch pinch and double-tap through CDP touch input with 44 px targets, axe; mutations `tools/mutate_p18.py`, which refuses a mutant that does not parse or does not type-check as the build does (`tests/v1/unit/test_mutation_suites_parse.py` checks all eleven suites) | CI + before release |
| TUI | `tests/v1/tui/` | TUI screens driven by scripted keys through `term.py`'s patched backend (today's `tests/harness.py` pattern). *As built (P17):* acceptance T02–T15, the terminal-injection boundary, phase-separation and import boundaries, transport, and the shared parity cases; mutations `tools/mutate_p17.py` | every commit |
| Design gates | `tests/v1/design/` | contrast over tokens × themes, keyframe properties, no backdrop-filter, container-query rule, tokens regenerated, CSP/no inline script | every commit |
| Client units | `clients/app/test/*.test.ts` (`npm test`, `node --test`, no framework) | pure SPA modules: presentation, cache invalidation, relations, destinations, commands (P16) | CI (`v1-client`) |
| Legacy suite | `tests/` (existing ~1,300 tests) | unchanged; guards the P0.5 seam edits and the legacy app until retirement | every commit |

### 1.1 The `CoreClient` contract and phase-tagged scenarios

The judge never imports Core internals and cannot wait for HTTP (P3.5) to be written, so P1
freezes `tests/v1/judge/client.py`: a `CoreClient` protocol with exactly the operations the
scenarios use — `submit_message`, `create_mission`, `get_mission`, `list_missions`,
`decide_approval`, `pause`, `resume`, `stop`, `route_why`, `status`, `digest`, `ack`,
`create_project`, `declare_constraint`, `import_meeting`, `list_knowledge`, `register_account`, `set_policy_rule`,
`set_resource_policy`, `events(after_seq)` — mirroring the command/query surface of
api-and-realtime §2. (`create_project` and `declare_constraint` were added in P4, D1 of
p4-design-gate.md: the S7 rig registers its fixture repository and constraint through the
contract, never through Core internals. `list_knowledge` was added in P6, D8 of
p6-design-gate.md: K1–K3 judge what a pass produced through the contract. `submit_message`
is implemented in both bindings in P7: it posts the turn and returns Archeus's reply once Core
has settled what the turn set in motion; the judge's default Core is offered a recorded brain,
p7-design-gate D8. P12 added the session and checkpoint operations — `register_session`,
`launch_session`, `get_session`, `list_sessions`, `session_brief`, `resume_session`,
`handoff_session`, `link_session`, `close_session`, `checkpoints`, `handoff_execution`
(p12-design-gate §19, §21): C1–C14, H1 and R1 judge continuity through the contract, on two
fake session harnesses and a terminal that records instead of opening. P13 added
`verifications`, `decide_verification`, `reviews`, `review` and `abandon_integration`
(p13-design-gate §21): V01–V15 judge what was verified, decided and reviewed through the
contract; nothing in it writes evidence. P14 added `create_automation`,
`set_automation_state`, `automations` and `automation` (p14-design-gate §17): S10 and S10b
judge automation through the contract; nothing in it appends an event. P15 added no contract
operation: it made the rig's `device(name, scopes)` and `revoke(device)` real — a client paired
through the real routes, returned as an `HttpClient` holding its own token, with `open_stream()`
(p15-design-gate §19); credentials exist only over HTTP, so the in-process binding skips them.)
Two bindings: `InProcessClient` (P1–P3, calls the
application layer directly) and `HttpClient` (P3.5 onward, HTTP + SSE). Every scenario runs
against both once HTTP exists.

Tags are per **test function**, not per file: a scenario file holds one function per
sub-behaviour, and each function that cannot pass yet is `@pytest.mark.xfail(strict=True,
reason="phase:P<n>")`, where `P<n>` is the phase that makes *that function* pass. This is how a
phase acceptance that names part of a scenario ("S4 (routing part)", "G1 at the persistence
level") is met while the rest of the scenario stays pending. `test_traceability.py` fails when a
tag names a phase outside the row's range in §2, or when the last function of a row is tagged
with anything other than the row's last phase; `strict` makes a function that starts passing
early fail until its marker is removed. A row is green when all its functions pass.

Fixtures: `FakeHarness` (a real subprocess following the process I/O contract, scripted: emits
tool calls, usage, `DECISION:` lines, limit errors, crashes, pressure),
`FakeUsageFeed` (drives window utilisation over fake time), `FakeClock`, `FakeNotifier`,
`TempCore` (Core on a free port with a temp home), `SSEClient` (stdlib) with Last-Event-ID.
Like today's `conftest.py`, a guard fails any test that would spawn a real `claude`/`codex`
process unless marked `real_harness`, and no test writes outside its temp home: every V1 test
sets `ARCHEUS_HOME` to a temp directory (the resolver reads it at call time).

## 2. Traceability — every acceptance source → phase → test

Four sources define "V1 works": the prompt's 15 acceptance scenarios (**S**), the implementation
plan's scenarios A–G (**IP**), the specification's 18 acceptance criteria (**SP**) and the
release gate (**G**, implementation plan Phase 24 + PDF §32; the release gate is this plan's
P26 since 2026-09-28, see the renumbering note in the plan's §31.1). They overlap; this table merges
them so nothing is tested twice under different names or missed.

| ID | Requirement | Also covers | Judge test (`tests/v1/judge/`) | Phases |
|---|---|---|---|---|
| SK | Walking skeleton: create mission → stub plan/policy → fake execution subprocess → stub verification/review → COMPLETED, observed over SSE and in the SPA | — | `test_skeleton_vertical_slice.py` | P3.5 |
| S1 | Simple coding mission end-to-end | SP1–7, SP11–13, IP-B (part) | `test_s01_simple_mission.py` | P7–P13 |
| S2 | Long-running mission across multiple sessions | SP9, SP10, IP-D, G "resume after handoff" | `test_s02_long_mission_handoffs.py` (fake pressure at task 3 and 6) | P11–P12 |
| S3 | Multiple accounts/models registered; router respects priority | SP7, SP8, IP-C, G "routing deterministic and explainable" | `test_s03_multi_account_routing.py` (P10: both functions; unit and property tests in `tests/v1/unit/test_routing_units.py`) | P10 |
| S4 | Quota exhaustion → policy-controlled fallback; allocation ceilings never exceeded at start; halt at boundary on crossing | IP-C, G "priority/allocation work" | `test_s04_limit_and_fallback.py` (fallback allow / ask / deny variants; P10: the ceiling at start and the three fallback variants, the mid-run crossing is P12's) | P10–P12 |
| S5 | Human approval (plan and mid-execution action) | SP6, G "policies enforced" | `test_s05_approvals.py` (P9: a plan that asks, idempotent decide, a decided approval stays decided, no carry to the next plan version; single-use of a mid-execution action approval is P11's, p9-design-gate D21; expiry and step-up in `tests/v1/integration/test_policy.py`) | P9, P11 |
| S6 | Verification failure → replan (budget 2 → BLOCKED) | SP11, SP12, G "verification exists" | `test_s06_verify_fail_replan.py` (P8: a failed task replans into a new plan version; P13: the verification-driven functions, on a fixture repository whose tests fail, p13-design-gate D20) | P13, P8 |
| S7 | Repository reinspection and architecture drift | IP-G, G "repository re-inspection works" | `test_s07_drift.py` (fixture repo, commit that violates a constraint) | P4 |
| S8 | Meeting notes used as context | SP2 | `test_s08_meeting_context.py` (import → mention → package cites it with reason) | P5–P6 |
| S9 | Feedback becomes durable knowledge; supersession | SP14 | `test_s09_feedback_to_knowledge.py` (driven through `submit_message`: which message is feedback, and which preference it supersedes, is intent — P7; P6 builds the promotion and supersession it lands on, p6-design-gate D1) | P7 |
| S10 | Event triggers automation (model added → documentation) with loop guard | SP15, IP-F, G "event-driven automation exists" | `test_s10_automation.py` (+ `test_s10b_loop_guard.py`: self-triggering automation escalates at depth 3, suspends after 3) | P14 |
| S11 | Mobile control: observe, pause, resume, approve from a paired device | SP16, SP17, IP-E, G "remote control works" | `test_s11_remote_control.py` (device token over the remote host allowlist; pause is cooperative) | P15 |
| S12 | Explain why a resource was selected | SP18 | `test_s12_route_why.py` (answer generated from the RouteDecision, no model call; replay equality) | P10 |
| S13 | Ask current state across projects | SP13 | `test_s13_status.py` (deterministic status without brain; brain summary links every claim) | P4, P7 |
| S14 | "What changed while I was away?" — per-user cursor, cleared on any device | — | `test_s14_digest.py` | P4, P15 |
| S15 | Idea → mission | IP-A | `test_s15_idea_to_mission.py` | P7 |
| SP3 | Archeus challenges or clarifies when necessary | — | `test_sp03_challenge.py` (conflicting DECISION in context → Challenge block, mission BLOCKED until choice) | P7 |
| G1 | Domain state persistent; mission independent of any session | SP9 | `test_g01_restart_survival.py` (kill Core mid-mission; restart; reconcile; continue) | P2–P3, P11 |
| G2 | Context selection explainable and provenance-aware | — | `test_g02_context_package.py` | P5 |
| K1 | Knowledge builds with no Claude Code installed | ADR-0022 | `test_k01_knowledge_without_claude.py` (fake `headless` harnesses only; a harness not declaring `headless` never elected; your choice honoured; the RouteDecision records the election and its rejected candidates) | P6, P10 |
| K2 | Structured extraction across mechanisms | ADR-0006, ADR-0022 | `test_k02_structured_extraction.py` (native and prompted both valid; invalid retried once, then no knowledge; provenance names harness and model) | P6 |
| K3 | Project setup completes after the knowledge pass | plan P6 | `test_k03_project_setup.py` (success, failure, gated by ADR-0021: the project stays usable; the result is a count) | P6 |
| C1 | Resume after an interruption: the session is found, the mission reconstructed from current state, a fresh package assembled, the changes surfaced | p12-design-gate §9 | `test_c01_resume_continuity.py` | P12 |
| C2 | An execution that moved while the session was away is shown as it is now | — | `test_c01_resume_continuity.py` | P12 |
| C3 | Cross-harness hand-off: the target gets what Core renders, no provider-private state | ADR-0023 | `test_c03_session_handoff.py` | P12 |
| C4 | A model switch keeps the session, its provider session and its mission; another harness's model is refused | ADR-0022 | `test_c04_session_model_and_concurrency.py` | P12 |
| C5 | Two sessions on one mission: each resume reads the durable changes the other made | — | `test_c04_session_model_and_concurrency.py` | P12 |
| C6 | A stale context package is rebuilt through P5; a fresh one is reused | P5 | `test_c04_session_model_and_concurrency.py` | P12 |
| C7 | A session grants nothing; a continuation meets the policy as it is now (P9) | P9 | `test_c04_session_model_and_concurrency.py` | P12 |
| C8 | Sessions survive a Core restart and no launch is replayed | G1 | `test_c01_resume_continuity.py` | P12 |
| C9 | Hand-off lineage is explicit and the source is never written | ADR-0023 | `test_c03_session_handoff.py` | P12 |
| C10 | No secret reaches a session, an event, a launch or an artifact | — | `test_c03_session_handoff.py` | P12 |
| C11 | The same resume request twice changes nothing | — | `test_c01_resume_continuity.py` | P12 |
| C12 | The same hand-off request twice makes one target | — | `test_c03_session_handoff.py` | P12 |
| C13 | Current durable state wins over what a checkpoint recorded | — | `test_c01_resume_continuity.py` | P12 |
| C14 | Missing context is reported, never invented; nothing to hand over is refused | — | `test_c03_session_handoff.py` | P12 |
| H1 | Cross-harness session hand-off (moved from §6 by the P12 gate) | ADR-0023 | `test_h01_r01_session_harnesses.py` | P12 |
| R1 | A session resumes on its own harness's configuration (moved from §6 by the P12 gate) | ADR-0023 | `test_h01_r01_session_harnesses.py` | P12 |
| V1 | The outcome is verified from evidence Core observed, never from an exit code: a wrong change fails (V01/V14), a right one is merged into the mission branch and reviewed (V02/V15), nothing to run waits for you (V03), a failing criterion replans (V05), tests passing with no change fail (V11) | SP11, SP12, p13-design-gate §24 (V04, V07–V10, V12, V13, M01–M06 in `tests/v1/integration/test_verification.py` and `test_provenance.py`) | `test_v01_outcome_verification.py` | P13 |
| V6 | A retried task is verified on the attempt that ended it, never on an earlier one | p13-design-gate §10 | `test_v06_attempts.py` | P13 |
| G3 | GUI/TUI/web/mobile use one backend model | SP17 | `test_g03_one_model.py` (same mission observed via SPA e2e, TUI script, CLI; P16: the GUI function passes through `SpaDriver`; P17: the TUI function passes through `TuiDriver`, which reads the Work row from the rendered frame) | P16–P19 |
| G4 | Audit trail exists | — | `test_g04_audit.py` (every transition has an event with actor + reason; approvals immutable) | P2 |
| G5 | Emergency stop exists (with and without Core) | — | `test_g05_estop.py` (STOP sentinel halts fake executions; `archeus estop` kills by pid+create_time with Core down) | P11, P20 |
| G6 | Security: approval boundaries and destructive-action controls | — | `test_g06_security.py` (DENY not overridable downward; execution scope cannot create missions; brain cannot approve; token in query string rejected; revoked device stream closed) | P3.5, P9, P15 |
| G7 | Harness adapters normalised and replaceable | — | `tests/v1/contract/test_adapter_contract.py` over fake + claude_code + codex fixtures (P11: fake and a recorded Claude Code stream; the Codex adapter and its recording are P20's, p11-design-gate D30) | P11, P20 |
| G8 | Legacy data migration tested | — | `test_g08_legacy_import.py` (fixture legacy home → idempotent import → counts/mappings) | P22 |

`tests/v1/judge/test_traceability.py` parses this table and fails if a listed test file does not
exist or if a judge test is not listed — the table cannot drift from the suite.

## 3. Focus areas the prompt calls out

| Area | Tests that must exist |
|---|---|
| Policy boundaries | precedence (GLOBAL→ACTION), locked rules, ALLOW_WITHIN_BOUNDARY path/branch/cost boundaries, `unclassified` exec treated as strictest, fail-closed hook when Core unreachable (Archeus executions) vs fail-open (interactive) |
| Account quotas | ceiling at start, halt on crossing, stale-usage penalty, `allocation_known=false` budget path, brain reserve |
| Fallback | allow/ask/deny; never silent; affinity dropped only on resource-attributable failure |
| Session hand-off | pressure computation from recorded usage; checkpoint content derived from diff/verification/decisions; mission/task state unchanged across hand-off; account change always creates a new session |
| Failure recovery | Core crash between INTENT commit and spawn → ABANDONED; crash mid-execution → adopt or kill; PID reuse does not kill a stranger (create_time mismatch) |
| Stale knowledge | superseded items excluded; stale items labelled and down-ranked; expired lesson revalidates |
| Architecture drift | each constraint kind has a positive and a negative fixture; prose-only constraints reported as uncheckable |
| Automation loops | depth cap escalates; rate limit; suspension; claim-and-advance never double-fires under concurrent ticks |
| Human approvals | replay (same action twice → second needs a new approval), expiry, superseded on replan, idempotent double-tap from two devices |

## 4. Mutation verification and floors

- Every gate in `tests/v1/design/` and every judge test is mutation-checked once when written
  (break the rule it guards, watch it fail, record the mutation in the test's docstring), as the
  repo does today.
- The E2E UI run counts checks and fails below a floor (starting floor = number of destinations
  × inspector tabs + approval flow steps).
- The judge suite asserts it collected at least as many scenario tests as the §2 table has
  rows; the floor is derived from the table, never typed as a number.

## 5. CI

- Existing `test` job unchanged (legacy suite; installs only pytest).
- New `v1` job: `py -m pytest tests/v1 -q` (stdlib + pytest only), then `npm ci && npm run build
  && npx playwright test` for the SPA (Node only in CI and release, never at runtime).
- Contract tests against real harnesses: manual/weekly workflow with sandbox accounts; never on
  pull requests (quota and secrets).
- Known runner limitation: `test_writer_throughput_is_at_least_500_commands_per_second`. 500/s
  is the target on a developer machine and CI asserts a 200/s regression floor (plan C12). The
  hosted Windows runners measured 68–154 commands/s across the P4 CI runs, with the writer
  unchanged and the same commit passing on one Python version and failing on the next, so the
  test fails there by the runner's fsync cost, not by a regression. The floor, the writer and the
  WAL/FULL-sync pragmas stay as they are: lowering any of them to make the runner pass would
  measure the runner instead of Archeus.

## 6. Scheduled scenarios (current-product parity, ADR-0022 / ADR-0023)

Required by the 2.8.0 behaviour of the current product (commits `94b90f9`, `26f983b`). Each
moves into the §2 table, with its strict-xfail judge file, at its phase's design gate — not
before, so §2 stays exactly what the judge collects. **K1–K3 moved into §2 with P6**
(p6-design-gate §10); **R1 and H1 moved into §2 with P12** (p12-design-gate §21), as C1–C14 joined it. All run on fake harnesses: a second fake
harness id added without any domain change is how "a new harness needs no new entity" is proven.

| ID | Scenario | Asserts | Phase |
|---|---|---|---|
| K1 | Knowledge builds with no Claude Code installed | only a fake `headless` harness is installed → the knowledge pass runs on it; a harness not declaring `headless` is never elected; the user's own-call choice (harness + model) is honoured when installed and capable; the RouteDecision records the election and its rejected candidates | P6 (election), P10 (router) |
| K2 | Structured extraction across mechanisms | a `native` and a `prompted` adapter both yield items that pass Core's schema validation; invalid prompted output is retried once, then asks (ADR-0006); provenance names harness and model | P6 |
| K3 | Project setup completes after the knowledge pass | create project → deterministic assessment → initial knowledge pass queued; the project stays usable when the pass fails or is gated by ADR-0021, and its result is counted, never assumed a collection | P6 |

## 7. Visual architecture gates (P19.5, ADR-0024…0029 — being built slice by slice)

Each gate is mutation-verified (remove the feature, the gate must fail) and runs in the v1-client
CI job. They are listed here so the phase cannot close without them; they are not rows of §2
because most have no test file yet. A row marked **built** names its tests; its mutants are
`tools/mutate_p19_5.py` (N01-N59, 59/59 killed, 2026-09-30: the foundation N01-N25, the halo
N26-N37, the travelling marker N38-N59; the copy/id gate and Details N71-N83, 13/13 killed,
2026-10-01; one name per command, the automation run and the repository inspections N84-N88, 5/5
killed, 2026-10-02; R2's legend, expand all / collapse all and tier words N89-N102, 14/14 killed,
2026-10-02; R3's hull, depth tiers, cored node, receding lines and impact view N103-N119, 17/17
killed, 2026-10-02; R5's row pulse and change rule N120-N139, 20/20 killed, 2026-10-02; R6's thread line N140-N153, 14/14 killed, 2026-10-02; R7's mark, orbit, favicon and operations strip N154-N180, 27/27 killed, 2026-10-02; R8's Now — the state sentence, upcoming, recent decisions, the automation line and the live map — N181-N207, 27/27 killed, 2026-10-02; R10a's Pause all / Resume all and `/v1/status` `resumable` N208-N222, 15/15 killed, 2026-10-02, with N60, N62, N64 and N68 re-anchored on the shared `commands.resumable` and the longer status line, unchanged in meaning; R10b's absolute priority N223-N229, 7/7 killed, 2026-10-03; R9's static skeleton N230-N233, 4/4 killed, 2026-10-03). The browser gates run on the page's
frozen clock (`tests/v1/e2e/motion.py`: Playwright's clock, a frame counter over the fake
`requestAnimationFrame`, `document.getAnimations()`, canvas pixel reads, a stream frame injected
over the tab channel), never on a sleep; the unit gates on `test/motion-harness.ts` (a frozen loop
host, a recording canvas, `renderAt(scene, timeline, t)`).

| Gate | Asserts |
|---|---|
| idle invariant (**built**) | with no live execution, no arriving change and no input: 0 rAF callbacks and 0 running `Animation` objects over 10 s — on every destination and the graph, and after a rerender, a reconnect-and-resync and a remount (`test_spa_motion.py::test_idle_archeus_runs_no_frame_and_no_animation`, 10 s of frozen page time; `motion.test.ts` idle tests at the loop and the timeline) |
| motion registry (**built**) | every keyframe, transition and `Loop.animate` id is a built entry of `motion.json`, and every built entry is really bound; no WAAPI; an `approved` id is used nowhere; every entry has its metadata, `replay: false` (`gen_ui.motion_problems`; design gates `test_every_keyframe_and_transition_is_a_registered_motion`, `test_every_loop_animation_is_a_registered_built_motion`; `motion.test.ts`); transform/opacity only, no `infinite` (the P16 gates) |
| caps (partly built) | registry: marker ≤ 600 ms, ≤ 8, oldest dropped; pulse 240 ms, ≤ 12, ≤ 1 / 2 s per edge (`test_the_motion_registry_holds_the_approved_budgets`); the timeline enforces cap and `over_cap` (`motion.test.ts` caps). **Built for the marker:** exactly 600 ms and 8, eight coexisting on one edge, the ninth dropping exactly the oldest, a resent batch recreating none (`marker.test.ts`); in the browser nine batches 50 ms apart leave eight travelling (`test_spa_marker.py`, the canvas's `data-markers`). Chips ≤ 3 per row, thread 1, orbit ≤ 1 / 5 s are registered and gated when built. **Built for the orbit (R7):** one 900 ms turn (`--dur-orbit`), at most one per 5 s, cap 1, an event at or below the newest presented seq never turns (`orbit.test.ts`; `test_spa_strip.py`). **Built for the row pulse (R5):** 240 ms, at most 1 / 2 s per row, no cap on the DOM (rulebook A-02), handled in event order (`rowpulse.test.ts`; `test_spa_rows.py`). The activity chip is **not built**: R5 deferred it because its text has no source yet — Core's execution read records no current action, and the rulebook, ADR-0024 §6 and the registry do not say which record supplies it |
| determinism (**built**) | `renderAt(t)` pictures equal for equal (state, t), different while a motion is active, the static picture once it ended; `timeline.ts`, `render.ts` and `layout.ts` read no clock and no random, and no file of `src/graph/` or `src/state/` calls `Math.random` — the rule's scope as ADR-0024 §4 clarifies it (animation, rendering, layout, presentation state); the idempotency-key fallback in `data/commands.ts` is an operational identifier, outside it |
| no replay (**built** for the pulse, the marker and the row pulse) | an event at or below the newest seq a motion presented is refused, and a running presentation keeps its start (`motion.test.ts`); in the browser a historical frame heard again — mid-pulse and after the rate window, or an older seq — fires no pulse, a newer one does (`test_a_historical_event_heard_again_never_replays_or_restarts`). The re-sent frame is injected over the tab channel: Core is not asked to re-send one. The marker: the same seq mid-travel, after it, across a lost stream and a resync, and after a remount starts none and never restarts the running one; a newer seq starts exactly one (`marker.test.ts`, `test_spa_marker.py`). Threads join the gate when built |
| travelling marker (**built**, graph) | one marker per `execution.*` frame whose subject is a loaded execution with a drawn, live `executions.task_id` edge — none for another kind, another event, an unloaded execution, an ended one or a frame with no seq; from the execution to its task, linear, head at the source at t = 0, half way at 300 ms, at the task by 600 ms, gone after; 3 px head, 12 screen-px tail in `--thread`; one block of its own ops after the static picture (nothing else changes); degraded frames → the pulse's form; reduced motion → none drawn, the event counted as presented, the 2 px static live edge; the mirror says "— live now" on the execution's relation to its task; one marker is a bounded run of frames and the loop parks after (`marker.test.ts`; `test_spa_marker.py`, framebuffer reads of thread-ink pixels along the edge at start, mid and end). **Known flaky (recorded 2026-10-03):** `test_spa_marker.py::test_the_marker_travels_once_from_the_execution_to_its_task` fails about one run in four at its first framebuffer read ("the marker begins at the execution: None", about 2 s in), alone and in the full suite; reproduced on `04eabe9`, the commit that introduced it, so it predates every later slice. It is tracked apart from P19.5 and is not to be made green by changing production behaviour |
| halo lifecycle (**built**, graph) | halo ⇔ presentation class `active` in the read the view holds; two static strokes at `halo-inner`/`halo-outer`, one solid ring under forced colours or reduced transparency; in the static layer, zero frames; unchanged across a lost stream, a resync whose re-read fails, a re-read of the same state and a remount; kept under reduced motion; gone once a read shows the work not live; every other node drawn exactly as without it; the mirror says "live work now" (`halo.test.ts`; `test_spa_halo.py::test_the_halo_marks_live_work_until_core_says_it_stopped`, framebuffer reads on the halo radius, the stop through `POST /v1/executions/{id}/stop`). The row-glyph ring (rulebook A-03) comes with the list slice |
| thread (T2 **built**, R5; T1 **built** on Now, R6) | T1 reaches the row named by `Message.links`, once; T2 marks exactly the digest's changed rows; left-edge rule used by nothing else. **Built (T2):** every list whose objects the digest can name — Work's missions and ideas, Now's happening-now and Needs you, World's projects, a project's repositories, Knowledge and a knowledge item's supersession chain, Attention, Control's rules, automations and their runs, harnesses, accounts and sessions, and a session's lineage — carries the 2 px left-edge rule in thread ink and the words "changed since you looked" exactly when Core's digest names the row's object; Dismiss clears them with one 200 ms fade (A-06), at once under reduced motion; a clear 2 px edge keeps the layout still; no other rule draws on a row's left edge (`test_the_left_edge_of_a_row_belongs_to_the_thread`; `test_spa_rows.py`, row by row against Core's own digest, before and after an acknowledgement). Not here: the Relations list and the TUI (P19), a session's own "what changed since this session last looked" (its cursor, not the user's). **Built (T1, R6):** a new Archeus message — heard by its `message.created` frame, read with the conversation — whose `Message.links` name an object with a row on Now draws one line in thread ink (1 px, 1.5 px at 2×) from the message to the first such row: placed by measurement, drawn on once in `--dur-travel` (600 ms) by transform and opacity, then gone, one at a time (`thread-travel`, cap 1, refuse); never again for a message already handled, a frame heard again, a lost stream or a fresh load; no row on screen, no line; reduced motion, no line; high contrast 2 px in `focus`, forced colours 2 px in `Highlight`; every such message says "Archeus updated …" in the polite live region; what stays is R5's rule, on the row and on the message's card or link (a link with no card is shown as one) while the digest names the object (`thread.test.ts`; `test_spa_thread.py`, the line's two ends against the message's and the row's boxes, the replies from the control grammar). Deferred: thread tints (no curated list exists, and Control → Appearance is P19's), the mission Now tab (per-mission conversations are P19's S1) |
| confidence styles (**built**) | EXTRACTED solid, INFERRED dashed, AMBIGUOUS dotted; the legend lists only tiers present in the loaded edges. **Built:** each tier's dash, a column edge solid (`graph.test.ts`); the legend's line rows are exactly the tiers the loaded edges carry — a column edge counts as recorded, AMBIGUOUS appears only once a loaded edge carries it (X-20), a tier Core does not define is never guessed — each drawn with its own dash in edge ink (`legend.test.ts`); in the browser the mission graph lists "recorded" alone (`test_spa_legend.py`) |
| legend and whole-graph commands (**built**, R2) | the legend (ADR-0025 §2) names, as a list of real checkboxes over swatches drawn with the renderer's own marks, every kind the loaded picture holds and every tier its edges carry, then the halo and the marker (under reduced motion, the static live edge); unticking a row hides that kind or tier from the drawing and nothing else — the mirror still lists it; "Expand all" / "Collapse all" and the keys E / C reach the full and the top-level picture, twice as once, from a partial one too, and a collapse that hides the focused node moves the keyboard to what stands for it; Space still toggles one node; tiers read "recorded", "suggested by Archeus", "unclear" in the legend, the mirror and the Relations list, never the enum; none of it sends a request, moves the URL or stores anything (`legend.test.ts`; `test_spa_legend.py`) |
| impact view (**built**) | reachable set equals BFS over recorded relations in the loaded neighbourhood, bounded by hops. **Built:** "What does this affect?" on the focused node (toolbar toggle, 1–3 steps, default 2; Esc or the toggle leaves it) reaches exactly the loaded objects within the bound over recorded relations, both ways, never across a suggested one (`model.impactOf`); the edges it crossed are drawn as the path highlight, what it reached stands on its drawn ancestor when collapsed, everything else at alpha-tier2; a status line and the mirror say it in words ("affected, 2 steps from …"), and it covers this loaded view only (`constellation.test.ts`; in the browser its count equals a breadth-first search over Core's own read at 2 and 1 steps, `test_spa_constellation.py`) |
| constellation (**built**, R3) | the project hull is one filled path per drawn project with drawn members, under every stroke, `text` at `hull` (`hull-focus` when the focus is in it), gone when the project is collapsed or unticked, a 1 px outline when opaque; depth by drawn hop distance from the focus — 0–1 full, 2 `alpha-tier1`, 3+ or unconnected `alpha-tier2`, opaque 1 / 1 / .64, nothing dimmed without a focus; a live node (the halo's set) has a core of thread ink at `CORE` × its radius, no other node does; an edge recedes to `alpha-recede` unless it is a recorded edge of the focus, a selected, path or live edge, keeping its tier's dash; opaque, nothing recedes; the mirror says "in project …" and "N steps from …" (`constellation.test.ts`; `test_spa_constellation.py`, framebuffer counts of the hull's tint expanded, collapsed, unticked and under forced colours, and thread ink at a running attempt's centre) |
| colour separation (partly built) | focus ≥ ΔE 20 from every state colour (built: `test_focus_is_never_read_as_a_state`, `test_the_terminal_focus_is_never_a_state_colour`); red used only by blocked/failed-needing-action; tints 3:1 and ΔE ≥ 30 (tints not built: R6 deferred them — the curated list is not in the repository) |
| text equivalents | every registry animation has a live text equivalent present in the DOM |
| loading skeleton (**built**, R9; A-12) | while a list's read is pending, `Loadable` shows three static skeleton rows in the shape of a list (`data-skeleton`, a `status` region) and says "Reading X…" to a screen reader only; nothing in it animates — no animation, transition or gradient (no shimmer); the bars keep an outline under forced colours; Core's rows replace it when the read answers (`test_spa_loading.py`, the read held by the browser until released) |
| reprioritise (**built**, R10b; D-14) | one number per mission, set by Core's one command: the mission inspector's header shows Core's `priority` in a labelled field (0 by default) and "Set priority" sends exactly that integer to `POST /v1/missions/{id}/reprioritize` with the version on screen and a key per press; a fraction is refused before it is sent and says why; the field follows Core when the priority is set elsewhere; an ended mission (no trigger leaves its state: COMPLETED, CANCELLED) offers none, as Core refuses it there; a client without `control` is told why; a Work row says a priority other than 0, from Core's list; nothing is draggable — drag and Alt+↑/↓ are the recorded deviation (rulebook §46.1); axe clean; 44 px and no sideways scroll on a phone (`present.test.ts` `ended`; `test_spa_priority.py`) |
| Now (**built**, R8) | ≤ 7 blocks; state sentence derived from counts; no greeting. **Built:** Now's blocks are Needs you, Happening now, Since you last looked, Upcoming, Recent decisions, the Live map and the conversation, in ADR-0027 §4's order, at most seven, a block with nothing to show not drawn; the state sentence equals Core's counts (the unsettled missions, `/v1/attention`) in the `display` role and greets no one; Upcoming is exactly Core's missions in the presentation classes `approved` and `planning`; Recent decisions is exactly the five newest of the decided approvals, the `fallback` route decisions and the CONFIRMED DECISION knowledge (never a candidate), each row linking its object and able to carry the T2 rule; the automation line counts the ENABLED automations and links to them; the live map holds exactly the active missions and the attempts `/v1/status` lists as live, from the depth-1 graph read around each, at most 40 nodes, drawn from 1000 px and not at 999 px or on a phone, without the graph toolbar, framing what arrives later, parked when nothing moves and drawing no frame for a re-read of the same live work, drawn under reduced motion and forced colours, and every node opening the full graph focused there (`now.test.ts`; `test_spa_now.py`, against Core's own reads) |
| favicon / orbit (**built**, R7) | favicon and orbit state follow idle / working / needs you / disconnected. **Built:** the node is hollow while this client is not connected, else attention while `/v1/attention` counts anything, else active while `/v1/status`'s live work holds an attempt in presentation class `active`, else neutral (rulebook §7.1's order); the favicon is the same glyph on the dark tile with its node in the same state, still; a batch of `execution.*` frames turns the node once round the orbit — two transform-only CSS animations (`orbit-turn` and the `orbit-counter` that keeps the node round), 900 ms, ease-in-out, parked where it began, no animation frame — at most once per 5 s, never for a re-sent or older event, a lost stream, a resync or a route, never under reduced motion (the colour stays); an execution frame makes `/v1/status` stale, since its live work moved (`orbit.test.ts`; `test_spa_strip.py`: the node's box held at 0, 450 and 225 ms against its rest and the orbit's centre). The operations strip (O-1) is a navigation landmark named Operations on every page: "N running · N needs you · N clients" equal to Core's own reads (running = missions with an attempt running; clients = devices whose presence is connected), each linking to its list (Now, Attention, Control → Clients), the status read's freshness, and the emergency stop behind its confirmation (Cancel first) or, once Core reads it disarmed, "Emergency stop engaged" linking to Control → About where it is re-armed; its words are said in a status region only when they change and at most once per 30 s; a phone keeps the mark and the counts; axe finds nothing serious in the header. The mark is the site's glyph in `currentColor`, 20 px, beside "Archeus" and on the boot screen ("Connecting to Archeus…"), nowhere else; the app icons are the tile mark from `tools/make_icon.py`, not the Attention diamond |
| framebuffer probes | halo (built), travelling marker (built), hull (built), cored node (built), focus and edge style pixels at known node positions (not screenshots) |
| frozen-clock captures | every surface × theme × width × state (ADR-0029), human-reviewed |
| innerText (**built**) | no raw ids, JSON or hashes in the default view; one command name per command. **Built:** every destination, Control section, mission, execution, session and knowledge tab, and the plan, task, route, policy, verification, project, repository, automation run and context package inspectors, and the project page's "Recent inspections" read open, read as a person reads them (visible text and accessible names; a closed disclosure renders only its summary) against a Core holding an account, a project with a repository, an automation, a second one enabled so that the deploy completing fires it, a lesson and a mission that asked before it deployed, carry no Archeus id (Core's own `ids.PREFIXES`, whole or shortened), bare ULID, JSON or hex digest; every Details is closed, titled "Details" and holds label/value rows only; it holds the object's identifiers whole, equal to what Core returns, and opening it shows them; names, states, the account label and the automation's sentences stay on screen (`test_spa_copy.py`; the patterns' own positive and negative cases without a browser; `present.test.ts` for the split into words and identifiers, Core's sentences, automations and usage; design gate `test_no_view_renders_json`). One name per command is read from the source, so a button that only a rare state renders is held too: a Core command (its API call and the decision it carries) has one name everywhere, and a name several commands share must be the bare verb Core gives each of them, sent to whichever object the page is about ("Stop" a mission, "Stop" an attempt), while a name that says more than the verb ("Accept result") names exactly one command (design gates `test_one_name_per_command` and `test_the_command_name_rule_fails_what_the_rulebook_found`). The two collisions rulebook §2.5 recorded are gone: a verification that waits on a person is "Mark passed" / "Mark failed", after the states it moves to, rejecting a knowledge proposal is "Reject" in Attention as it is in World, and "Dismiss" is the digest's alone. Core's own sentences still name objects by id (`authorization.py`, the router); the client renders each as a link named by its object (`Prose`), and rewording them is Core's |

## 8. Conversation, account-protection, live-work and theme gates (ADR-0041…0044, decided 2026-09-30)

Not built; listed so the owning slice or phase cannot close without them. Each is mutation-verified
in the phase that builds it (§4). Full wording and mutations:
[ARCHEUS_V1_CONVERSATIONAL_ORCHESTRATION.md](ARCHEUS_V1_CONVERSATIONAL_ORCHESTRATION.md) F4.

| Gate | Owner | Asserts |
|---|---|---|
| AP-1 protection invariant | AP-1 | over generated snapshots no `last_resort` account is elected while a `normal` candidate survives, whatever its affinity, preference or priority; no `explicit_only` account is elected unless a user-device preference or pin names it; a set budget eliminates a windowed account when reached; a `cost_*` budget on an account reporting no cost is refused at write; unknown usage is never read as 0 |
| G1 chat approve | P19 (S3) | a chat `approve` is the card's decision: same `action_hash`, step-up, idempotency |
| G2 all-scope verbs (**built**, R10a) | P19.5 Core slice | `pause all` / `emergency stop` reach the strip's commands; e-stop confirms. **Built:** the strip and Work offer Pause all (no confirmation: Resume all inverts it) and, exactly while `/v1/status` `resumable` is non-empty, Resume all; both go to their own route with the `control` scope and one idempotency key per press, and a client without `control` is told why; Pause all pauses every executing mission and the running count follows Core; Resume all resumes exactly what `resumable` named, never an older batch's mission, one paused by hand or one resumed and paused again by hand; a Pause all that pauses nothing leaves the newest batch; a second Resume all changes nothing; `resumable` and Resume all share `commands.resumable` (`test_spa_pause_all.py`, `test_p195_core.py`) |
| G3 no widening without confirmation | P19 | no brain output applies a widening directive or a standing change; the policy route stays `admin` |
| G4 narrowing with source | P19 | a narrowing directive lands on the mission with its `message_id`; an unresolved name is a clarification, never a guessed id |
| G5 explanation card | P19 | the `route_explanation` card equals the RouteDecision record |
| G6 one live derivation | P21 | `live_work` lists exactly the live executions and own calls without an outcome; the `status` verb and `/v1/status` agree |
| G7 route preview | P22 | a plan task's preview equals the dispatch decision for an unchanged snapshot |
| G8 own calls visible, still | P21 | an in-flight own call is listed and counted on its account, and animates nothing |
| G9 protection classes and lift | AP-1, P22 | as AP-1, plus the lift is scoped to the naming mission or project |
| G10 budgets always | AP-1 | a budget on a windowed account is enforced; none set → behaviour unchanged |
| AP-UK unknown usage (ADR-0048) | AP-1 | an adapter's absent figure is `None`; every end of a consumer that ran writes one ledger row with its `basis`; a period with a `partial` or `none` row makes a budget unevaluable and eliminates the account; a lower bound reaching the budget reads "reached"; a budget on an undeclared measure is refused at write |
| AP-CC concurrency over live work (ADR-0048) | AP-1 | live executions and in-flight own calls on one account key both count; at the cap a task and an own call are both refused; an own call past its maximum run no longer counts |
| AP-ID one account key (ADR-0048) | AP-1 | a task and an own call on the same unregistered home carry one key and a review is routed away from it; a second registration of a home is refused; `home_ref` cannot change |
| AP-RT no election outside the router (ADR-0048) | AP-1 | no V1 module imports `rotate`; with no registered account a harness offers exactly one fixed candidate; a registered account removes it |
| AP-LG legacy coexistence (ADR-0048) | AP-1 | across the AP-1 suites a fixture legacy home's settings, stores and rotation state are byte-identical before and after; AP-1 adds no import of a legacy writer |
| AP-WB no project or memory writes (ADR-0048) | AP-1 | a fixture project's files, timestamps and git status and a fixture legacy memory store are unchanged; AP-1 writes only `ARCHEUS_HOME` |
| AP-RB rollback (ADR-0048) | AP-1 | migration 0012 leaves a pre-migration copy of `archeus.db` in `ARCHEUS_HOME/backups/` that the pre-AP-1 build opens |

*Built in the AP-1 slice (ADR-0048 "As built"):* AP-1, G9 (the mission-scoped lift), G10, AP-UK,
AP-CC, AP-ID, AP-RT, AP-LG, AP-WB and AP-RB are `tests/v1/unit/test_ap1_units.py` and
`tests/v1/integration/test_account_protection.py`, mutation-verified by `tools/mutate_ap1.py`
(28 of 28 killed). G9's project half and G11–G13 stay with P21 / P22.

| Gate | Owner | Asserts |
|---|---|---|
| G11 project defaults | P22 | missions inherit and may narrow their project's defaults; only a user device sets them |
| G12 unknown stays unknown | P21 | consumption renders a missing reading as unknown, never a number |
| G13 effective policy parity | P21, P22 | the effective-policy read equals the router's inputs |
| G14 directive scope | P19 | ambiguous or task scope applies to the mission only; "never" / "from now on" produce a change card; no directive removes an elimination |
| T1 explicit theme | P19 | each explicit theme renders its token set whatever the emulated OS scheme |
| T2 system default | P19 | a first launch follows the OS scheme and contrast |
| T3 forced colours | P19 | `forced-colors: active` overrides any explicit choice |
| T4 contrast floors | P19 | the existing contrast gates run over every theme × role, unchanged |
| T5 persistence per client | P19 | the choice survives a reload, a service-worker offline start and a Qt shell restart (persistent profile); no Core read is needed |
| T6 before first paint; tints are not themes | P19 | `<html>` carries the theme attributes before the stylesheet paints (a `'self'` boot script); only the three token sets are selectable as application themes |

## 9. Legacy context migration gates (P22 tooling, P25.5 run — ADR-0045, ADR-0046, decided 2026-10-01)

Not built. Each is mutation-verified in P22 against fixture legacy homes (the existing G8 fixtures:
multi-account, codex, pi) and re-run in P25.5 on the user's environment. Design:
[legacy-context-migration.md](legacy-context-migration.md) §14–§18.

| Gate | Asserts | Mutation it must kill |
|---|---|---|
| MG-1 read-only source | after snapshot, dry run, import, verify and rollback, every legacy source has the same bytes, mtime and name; no lock or `.corrupt-*` file appeared | extractor calls a legacy loader that quarantines; a write-back |
| MG-2 determinism | two runs over one snapshot produce byte-identical source records and derived rows; a new snapshot reports every item unchanged / changed / new / gone | a timestamp or random id in a derived row |
| MG-3 losslessness | every `copied` item's bytes and every per-record fragment are recoverable from the snapshot; redactions are listed with field path and hash | a fragment dropped; an undeclared redaction |
| MG-4 provenance | 100% of migrated rows reach a source record through `derived_from`, with snapshot, path, key, hashes, transform and field diff | a row without `derived_from`; transform unrecorded |
| MG-5 no silent choice | an imported item conflicting with a V1 CONFIRMED item is a CANDIDATE with `contradicts` and a proposal; neither is superseded | newer wins silently |
| MG-6 project compatibility | manifests before and after cover git HEAD, refs, index, tracked, untracked and (where practical) ignored files, CLAUDE.md, AGENTS.md, `.claude/`, every `.archeus/` entry and the session folders; every difference is attributed by **positive evidence** to one owner — V1 (write ledger), approved mission (Execution + merge record), migration (run ledger; before cutover never a project path), legacy (inside a legacy-owned region), or user (presumptive, confirmed by the user; on fixture homes a presumptive user change fails) — never to the migration by timing | a migration writes a managed block without opt-in; a V1 write outside its ledger |
| MG-7 scope preserved | every record keeps its source scope; nothing becomes global | a project lesson imported globally |
| MG-8 rollback | before cutover the run's rows are withdrawn and V1-native rows kept; after cutover opt-in files restore to their recorded hashes **only where the current hash is the one V1 wrote** — a newer user edit is shown, never overwritten; the non-rollbackable register was shown and accepted; MG-1 and MG-6 pass after | a V1-native row withdrawn; a file not restored; a user edit overwritten |
| MG-9 dry run | a dry run writes only its scratch database and report | a write to the live database |
| MG-10 sensitive categories | every source lands in its ADR-0045 §9 category: no credential, API key or hash of a secret in any artifact, record, row or report (C); D sources are never copied; B records never enter a context package; a D → B exception needs its recorded `admin` command and secret scan | a settings key copied; a secret hashed; a bash log copied by default; a B record in a context package |
| MG-11 consent | no run or cutover starts without an `admin` user-device command; an update, restart or schedule starts none | cutover on upgrade |
| MG-12 V1 write boundary | a static walk of `archeus/` finds no write outside the four places of ADR-0046 (`ARCHEUS_HOME`; the V1-owned and shared entries of `<project>/.archeus/`; the three named project capabilities; the two user-level writes) | a new write site inside a project |
| MG-13 per-project isolation | a run over project A leaves every byte, the memory, context, rules, git state and legacy configuration of project B unchanged (manifest diff of B is empty); a source that cannot be assigned to exactly one project in scope fails the run closed | a run widened to a sibling folder; an ambiguous source imported |
| MG-14 legacy non-interference | with V1 Core running, inspecting and migrating other projects, an unmigrated project's legacy stores and managed blocks change only by the legacy app's own writers | V1 writes a legacy entry of `.archeus/` |
| MG-15 source accounting | 100% of source records are in the manifest and classified, every exclusion has a reason, and every record is cited by a derived row or the report (legacy-context-migration §17) | a record silently skipped |
| MG-16 dual-read | every §18 comparison runs, and every difference is classified and explained before a run can reach VERIFIED | a regression left unexplained; V1 preferred by default |
| MG-17 coexistence | one fixture holds four projects at once — V1, legacy, migration pending, V1 in its rollback window — and each behaves as legacy-context-migration §24.5 states: the marker is present exactly for A and D, legacy writers and hooks stand down only there, V1 hooks act only there, and no global mode exists | a global flag; legacy standing down for an unmarked project |
| MG-19 sessions as source material | a run creates no Execution from a legacy session and no Session row except by the user's action or the run's recorded `sessions` rule; every session appears in the manifest | a Session row per transcript; a date window applied by default |
| MG-18 unmigrated projects operational | for an unmigrated project, the legacy launcher, memory build, recall hook, CLAUDE.md block refresh and the project's own test and git commands behave exactly as on a machine without V1 | any legacy workflow broken by V1's presence |

## 10. Context capacity gates (P21 — ADR-0047, DECIDED 2026-10-01; built)

Built in the P21 D-26 slice except where the **Exists** column says otherwise (CX-7 waits on
AP-1, CX-16's migration half on MG-12 and MG-19). Each new gate is mutation-verified
(`tools/mutate_p21.py`, Z01–Z22) on fake harness scripts (a scripted `usage` emission, as S2
already does) and temporary git repositories, never on a real account or project. Design:
[ADR-0047](decisions/ADR-0047.md).

| Gate | Asserts | Exists | Mutation it must kill |
|---|---|---|---|
| CX-1 healthy continues | an execution whose reported pressure stays below the p12 threshold is never handed off and ends on its own | built: `tests/v1/integration/test_context_capacity.py` `test_cx1_below_the_threshold_never_hands_off`; S2 (P12) | a hand-off below the threshold |
| CX-2 approaching limit detected | a usage report at the threshold, or a PreCompact record, requests the hand-off at the next tool boundary | built: `tests/v1/integration/test_context_capacity.py` `test_cx2_…`, `test_precompact_…`; S2.1, p12 Y21 | pressure ignored; PreCompact ignored |
| CX-3 no blind continuation | a pressure continuation whose recorded end state equals that of any earlier link of its chain (A → B → A included), or cannot be measured, and that recorded no artifact, creates no continuation and ends `HANDING_OFF → ENDED_HANDOFF` (`checkpoint_written`) with `charged True`; the task takes `execution_failed_retry` while charged attempts remain, else `execution_failed_final` with `failure_class: context_insufficient`; the guard reads the Execution rows and artifacts, never a checkpoint; a user hand-off, a limit and a ceiling are never guarded | built: `tests/v1/integration/test_context_capacity.py` `test_cx3_…`, `test_no_git_workdir_…`; `tests/v1/unit/test_pressure_units.py` guard units | the guard removed (the loop runs until the scenario's own cap); the failure left uncharged; only the immediate predecessor compared; an unmeasurable end state read as progress; a `DECISION:` line counted as progress; the guard reading a Checkpoint |
| CX-4 checkpoint on every end | every end of an execution that ran, including a guarded one, derives one Checkpoint in the transaction of the end | built: P12; the guarded end's checkpoint in `test_cx3_…` | an end without a checkpoint |
| CX-5 provenance | a continuation carries `handoff_from`, `attempt + 1`, the same plan binding, the checkpoint id and `continuation` count; the hand-off reason names the window, its source and the usage offset | built: P12, and the basis in the reason (`test_cx2_…`, `test_why_and_status_…`) | the basis dropped from the reason |
| CX-6 state reaches the new session | the continuation's prompt carries the checkpoint rendering; mission and task states are unchanged by the hand-off | S2, C13 (P12) | a stale field shown as current |
| CX-7 protection holds at a continuation | over generated snapshots a continuation never elects a `last_resort` or `explicit_only` account that AP-1 would not elect for a first dispatch, whatever its window or remaining capacity | built (AP-1): `tests/v1/integration/test_account_protection.py` `test_a_continuation_never_goes_back_…`, `test_a_retry_never_goes_…`; `tools/mutate_ap1.py` A22, A23 | the continuation route skipping AP-1 |
| CX-8 unknown is not zero | with no window or no usage report, `pressure` and `remaining` are `None`, the item's quality is *unavailable*, and nothing renders 0 or "fits" | built: `tests/v1/unit/test_pressure_units.py` `test_no_window_or_no_report_…`, `test_precompact_…` | `None` coerced to 0 |
| CX-9 estimated, stale and signalled are labelled | a window from `harness_smallest` reads *estimated*; output recorded after the usage offset reads *stale*; a PreCompact record reads *signalled*, its 0.9 is never shown as a measured ratio, `used_tokens` holds only what a usage report said and `remaining` is `null`; none of them reads *reported* | built: `tests/v1/unit/test_pressure_units.py` (estimated, stale, signalled); `tests/v1/integration/test_context_capacity.py` PreCompact | the quality derived from the value alone; a PreCompact 0.9 recorded as `usage_source: harness_reported` |
| CX-10 a failed hand-off loses nothing | a continuation refused by P9 or P10 leaves the checkpoint, the task READY uncharged and the diff in place | P12 (§10.1 step 4) | the checkpoint written after the refusal check |
| CX-11 no compaction by Archeus | no Archeus code path asks a harness to compact or summarise; a harness's own compaction is recorded and turns into a hand-off, and the checkpoint's fields do not depend on the agent's context | built: `tests/v1/unit/test_pressure_units.py` `test_no_archeus_code_asks_a_harness_to_compact`, `test_the_guard_never_reads_a_checkpoint`; P12 PreCompact test | a compaction call added; a checkpoint field read from agent output other than `DECISION:` lines and the last error line |
| CX-12 deterministic | the same stream offsets and offers give the same pressure, basis, quality and guard outcome twice; quality needs no clock | built: `tests/v1/unit/test_pressure_units.py` `test_quality_reads_no_clock`; the digest is deterministic (`test_the_end_state_digest_…`) | a wall-clock staleness |
| CX-13 no unrelated disruption | a hand-off in mission A leaves every other execution, session and account state unchanged | built: `tests/v1/integration/test_context_capacity.py` `test_a_handoff_in_one_mission_disturbs_no_other` | a hand-off flag set by account or harness instead of by execution |
| CX-14 explainable | the `why` answer for a hand-off equals the execution's recorded reason, basis and checkpoint; no model call | built: `tests/v1/integration/test_context_capacity.py` `test_why_and_status_answer_from_the_record` | an answer composed from anything but the record |
| CX-15 idle is still | with no live execution nothing computes pressure, no request polls for it and nothing animates | ADR-0024 gates; pressure is computed only in the manager's read of a live stream (no timer, no request) | a context read on a timer |
| CX-16 legacy and projects untouched | a migration run writes no `context` basis and no `pressure` for any imported session; a hand-off, a checkpoint and a continuation change no byte of the project outside ADR-0046's namespace | partly: `tests/v1/integration/test_context_capacity.py` `test_cx3_…` shows a repository holds only what the agent wrote after a chain; the migration half depends on MG-12 and MG-19 (P22, not built) | a fabricated historical pressure; a checkpoint written into the repository |
| CX-17 a progressing chain stops on its resources | a chain whose every link makes progress continues with no count cap, and ends at the first P9 refusal, P10 refusal (a limit, a ceiling, provider terms, a budget), e-stop or user stop — uncharged, task READY; every link is a `live_work` item with its hand-off count; no continuation is created except in the transaction that ends a process | built: `tests/v1/integration/test_context_capacity.py` `test_a_chain_that_keeps_progressing_has_no_count_cap`; refusals E80, E81 (P12) | a continuation created on a timer or outside `record_handoff`; a refusal that charges; a hidden count cap |
| CX-18 the retry and the replan are bounded | after a guarded end the retry is a fresh execution (no `handoff_from`, no checkpoint suffix); `context_insufficient` is not in `NOT_RETRYABLE`, so a FAILED task reaches REPLANNING through `task_failed_retryable` while `replan_budget_exhausted` allows; with `max_attempts` and `max_replans` fixed, a scenario that never progresses ends in a bounded number of executions | built: `tests/v1/integration/test_context_capacity.py` `test_cx18_…`; `tests/v1/unit/test_pressure_units.py` `test_context_insufficient_stays_…` | `context_insufficient` added to `NOT_RETRYABLE`; a retry created as a continuation; the guarded end not counted by `charged_attempts` |
