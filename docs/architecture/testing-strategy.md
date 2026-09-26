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
| E2E UI | `tests/v1/e2e/` (Playwright, as `tools/smoke_gui.py` today) | SPA flows against the judge's Core fixture: every destination, inspector tab, approval flow; overflow/dead-space audit; animation loop parks | CI + before release |
| TUI | `tests/v1/tui/` | TUI screens driven by scripted keys through `term.py`'s patched backend (today's `tests/harness.py` pattern) | every commit |
| Design gates | `tests/v1/design/` | contrast over tokens × themes, keyframe properties, no backdrop-filter, container-query rule, tokens regenerated, CSP/no inline script | every commit |
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
p7-design-gate D8.) Two bindings: `InProcessClient` (P1–P3, calls the
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
release gate (**G**, implementation plan Phase 24 + PDF §32). They overlap; this table merges
them so nothing is tested twice under different names or missed.

| ID | Requirement | Also covers | Judge test (`tests/v1/judge/`) | Phases |
|---|---|---|---|---|
| SK | Walking skeleton: create mission → stub plan/policy → fake execution subprocess → stub verification/review → COMPLETED, observed over SSE and in the SPA | — | `test_skeleton_vertical_slice.py` | P3.5 |
| S1 | Simple coding mission end-to-end | SP1–7, SP11–13, IP-B (part) | `test_s01_simple_mission.py` | P7–P13 |
| S2 | Long-running mission across multiple sessions | SP9, SP10, IP-D, G "resume after handoff" | `test_s02_long_mission_handoffs.py` (fake pressure at task 3 and 6) | P11–P12 |
| S3 | Multiple accounts/models registered; router respects priority | SP7, SP8, IP-C, G "routing deterministic and explainable" | `test_s03_multi_account_routing.py` | P10 |
| S4 | Quota exhaustion → policy-controlled fallback; allocation ceilings never exceeded at start; halt at boundary on crossing | IP-C, G "priority/allocation work" | `test_s04_limit_and_fallback.py` (fallback allow / ask / deny variants) | P10–P12 |
| S5 | Human approval (plan and mid-execution action) | SP6, G "policies enforced" | `test_s05_approvals.py` (P9: a plan that asks, idempotent decide, a decided approval stays decided, no carry to the next plan version; single-use of a mid-execution action approval is P11's, p9-design-gate D21; expiry and step-up in `tests/v1/integration/test_policy.py`) | P9, P11 |
| S6 | Verification failure → replan (budget 2 → BLOCKED) | SP11, SP12, G "verification exists" | `test_s06_verify_fail_replan.py` (P8: a failed task replans into a new plan version; the verification-driven functions stay P13, p8-design-gate D13) | P13, P8 |
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
| G3 | GUI/TUI/web/mobile use one backend model | SP17 | `test_g03_one_model.py` (same mission observed via SPA e2e, TUI script, CLI) | P16–P19 |
| G4 | Audit trail exists | — | `test_g04_audit.py` (every transition has an event with actor + reason; approvals immutable) | P2 |
| G5 | Emergency stop exists (with and without Core) | — | `test_g05_estop.py` (STOP sentinel halts fake executions; `archeus estop` kills by pid+create_time with Core down) | P11, P20 |
| G6 | Security: approval boundaries and destructive-action controls | — | `test_g06_security.py` (DENY not overridable downward; execution scope cannot create missions; brain cannot approve; token in query string rejected; revoked device stream closed) | P3.5, P9, P15 |
| G7 | Harness adapters normalised and replaceable | — | `tests/v1/contract/test_adapter_contract.py` over fake + claude_code + codex fixtures | P11 |
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
(p6-design-gate §10); R1 and H1 are still scheduled here. All run on fake harnesses: a second fake
harness id added without any domain change is how "a new harness needs no new entity" is proven.

| ID | Scenario | Asserts | Phase |
|---|---|---|---|
| K1 | Knowledge builds with no Claude Code installed | only a fake `headless` harness is installed → the knowledge pass runs on it; a harness not declaring `headless` is never elected; the user's own-call choice (harness + model) is honoured when installed and capable; the RouteDecision records the election and its rejected candidates | P6 (election), P10 (router) |
| K2 | Structured extraction across mechanisms | a `native` and a `prompted` adapter both yield items that pass Core's schema validation; invalid prompted output is retried once, then asks (ADR-0006); provenance names harness and model | P6 |
| K3 | Project setup completes after the knowledge pass | create project → deterministic assessment → initial knowledge pass queued; the project stays usable when the pass fails or is gated by ADR-0021, and its result is counted, never assumed a collection | P6 |
| R1 | A session resumes on its own harness's configuration | parametrised over two harnesses: the resume argv carries the session's recorded model and effort in that harness's vocabulary, and never another harness's model, effort or defaults | P11 |
| H1 | Cross-harness session hand-off | parametrised source → target over two harnesses: the artifact carries the required context, the target adapter delivers it, a new Session has `handoff_from_session_id`, the source Session is unchanged, `session.handed_off` is recorded | P12 |
