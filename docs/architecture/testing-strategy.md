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
N26-N37, the travelling marker N38-N59). The browser gates run on the page's
frozen clock (`tests/v1/e2e/motion.py`: Playwright's clock, a frame counter over the fake
`requestAnimationFrame`, `document.getAnimations()`, canvas pixel reads, a stream frame injected
over the tab channel), never on a sleep; the unit gates on `test/motion-harness.ts` (a frozen loop
host, a recording canvas, `renderAt(scene, timeline, t)`).

| Gate | Asserts |
|---|---|
| idle invariant (**built**) | with no live execution, no arriving change and no input: 0 rAF callbacks and 0 running `Animation` objects over 10 s — on every destination and the graph, and after a rerender, a reconnect-and-resync and a remount (`test_spa_motion.py::test_idle_archeus_runs_no_frame_and_no_animation`, 10 s of frozen page time; `motion.test.ts` idle tests at the loop and the timeline) |
| motion registry (**built**) | every keyframe, transition and `Loop.animate` id is a built entry of `motion.json`, and every built entry is really bound; no WAAPI; an `approved` id is used nowhere; every entry has its metadata, `replay: false` (`gen_ui.motion_problems`; design gates `test_every_keyframe_and_transition_is_a_registered_motion`, `test_every_loop_animation_is_a_registered_built_motion`; `motion.test.ts`); transform/opacity only, no `infinite` (the P16 gates) |
| caps (partly built) | registry: marker ≤ 600 ms, ≤ 8, oldest dropped; pulse 240 ms, ≤ 12, ≤ 1 / 2 s per edge (`test_the_motion_registry_holds_the_approved_budgets`); the timeline enforces cap and `over_cap` (`motion.test.ts` caps). **Built for the marker:** exactly 600 ms and 8, eight coexisting on one edge, the ninth dropping exactly the oldest, a resent batch recreating none (`marker.test.ts`); in the browser nine batches 50 ms apart leave eight travelling (`test_spa_marker.py`, the canvas's `data-markers`). Chips ≤ 3 per row, thread 1, orbit ≤ 1 / 5 s are registered and gated when built |
| determinism (**built**) | `renderAt(t)` pictures equal for equal (state, t), different while a motion is active, the static picture once it ended; `timeline.ts`, `render.ts` and `layout.ts` read no clock and no random, and no file of `src/graph/` or `src/state/` calls `Math.random` — the rule's scope as ADR-0024 §4 clarifies it (animation, rendering, layout, presentation state); the idempotency-key fallback in `data/commands.ts` is an operational identifier, outside it |
| no replay (**built** for the pulse and the marker) | an event at or below the newest seq a motion presented is refused, and a running presentation keeps its start (`motion.test.ts`); in the browser a historical frame heard again — mid-pulse and after the rate window, or an older seq — fires no pulse, a newer one does (`test_a_historical_event_heard_again_never_replays_or_restarts`). The re-sent frame is injected over the tab channel: Core is not asked to re-send one. The marker: the same seq mid-travel, after it, across a lost stream and a resync, and after a remount starts none and never restarts the running one; a newer seq starts exactly one (`marker.test.ts`, `test_spa_marker.py`). Threads join the gate when built |
| travelling marker (**built**, graph) | one marker per `execution.*` frame whose subject is a loaded execution with a drawn, live `executions.task_id` edge — none for another kind, another event, an unloaded execution, an ended one or a frame with no seq; from the execution to its task, linear, head at the source at t = 0, half way at 300 ms, at the task by 600 ms, gone after; 3 px head, 12 screen-px tail in `--thread`; one block of its own ops after the static picture (nothing else changes); degraded frames → the pulse's form; reduced motion → none drawn, the event counted as presented, the 2 px static live edge; the mirror says "— live now" on the execution's relation to its task; one marker is a bounded run of frames and the loop parks after (`marker.test.ts`; `test_spa_marker.py`, framebuffer reads of thread-ink pixels along the edge at start, mid and end) |
| halo lifecycle (**built**, graph) | halo ⇔ presentation class `active` in the read the view holds; two static strokes at `halo-inner`/`halo-outer`, one solid ring under forced colours or reduced transparency; in the static layer, zero frames; unchanged across a lost stream, a resync whose re-read fails, a re-read of the same state and a remount; kept under reduced motion; gone once a read shows the work not live; every other node drawn exactly as without it; the mirror says "live work now" (`halo.test.ts`; `test_spa_halo.py::test_the_halo_marks_live_work_until_core_says_it_stopped`, framebuffer reads on the halo radius, the stop through `POST /v1/executions/{id}/stop`). The row-glyph ring (rulebook A-03) comes with the list slice |
| thread | T1 reaches the row named by `Message.links`, once; T2 marks exactly the digest's changed rows; left-edge rule used by nothing else |
| confidence styles | EXTRACTED solid, INFERRED dashed, AMBIGUOUS dotted; the legend lists only tiers present in the loaded edges |
| impact view | reachable set equals BFS over recorded relations in the loaded neighbourhood, bounded by hops |
| colour separation (partly built) | focus ≥ ΔE 20 from every state colour (built: `test_focus_is_never_read_as_a_state`, `test_the_terminal_focus_is_never_a_state_colour`); red used only by blocked/failed-needing-action; tints 3:1 and ΔE ≥ 30 |
| text equivalents | every registry animation has a live text equivalent present in the DOM |
| Now | ≤ 7 blocks; state sentence derived from counts; no greeting |
| favicon / orbit | favicon and orbit state follow idle / working / needs you / disconnected |
| framebuffer probes | halo (built), travelling marker (built), hull, focus and edge style pixels at known node positions (not screenshots) |
| frozen-clock captures | every surface × theme × width × state (ADR-0029), human-reviewed |
| innerText | no raw ids, JSON or hashes in the default view; one command name per command |

## 8. Conversation, account-protection, live-work and theme gates (ADR-0041…0044, decided 2026-09-30)

Not built; listed so the owning slice or phase cannot close without them. Each is mutation-verified
in the phase that builds it (§4). Full wording and mutations:
[ARCHEUS_V1_CONVERSATIONAL_ORCHESTRATION.md](ARCHEUS_V1_CONVERSATIONAL_ORCHESTRATION.md) F4.

| Gate | Owner | Asserts |
|---|---|---|
| AP-1 protection invariant | AP-1 | over generated snapshots no `last_resort` account is elected while a `normal` candidate survives, whatever its affinity, preference or priority; no `explicit_only` account is elected unless a user-device preference or pin names it; a set budget eliminates a windowed account when reached; a `cost_*` budget on an account reporting no cost is refused at write; unknown usage is never read as 0 |
| G1 chat approve | P19 (S3) | a chat `approve` is the card's decision: same `action_hash`, step-up, idempotency |
| G2 all-scope verbs | P19.5 Core slice | `pause all` / `emergency stop` reach the strip's commands; e-stop confirms |
| G3 no widening without confirmation | P19 | no brain output applies a widening directive or a standing change; the policy route stays `admin` |
| G4 narrowing with source | P19 | a narrowing directive lands on the mission with its `message_id`; an unresolved name is a clarification, never a guessed id |
| G5 explanation card | P19 | the `route_explanation` card equals the RouteDecision record |
| G6 one live derivation | P21 | `live_work` lists exactly the live executions and own calls without an outcome; the `status` verb and `/v1/status` agree |
| G7 route preview | P22 | a plan task's preview equals the dispatch decision for an unchanged snapshot |
| G8 own calls visible, still | P21 | an in-flight own call is listed and counted on its account, and animates nothing |
| G9 protection classes and lift | AP-1, P22 | as AP-1, plus the lift is scoped to the naming mission or project |
| G10 budgets always | AP-1 | a budget on a windowed account is enforced; none set → behaviour unchanged |
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
