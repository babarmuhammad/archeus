# Archeus V1 — Rearchitecture Plan

Status: planning complete, implementation not started. Branch `archeus-v1-rearchitecture`,
written 2026-09-23 against `main` @ `b778226`.

This is the entry point. It states decisions and links the topic documents instead of
restating them; where a topic has no document of its own (policy, planning, security,
observability, phases) the detail is here.

| Topic | Document |
|---|---|
| Design research, IA, flows, wireframes | [../design/ARCHEUS_V1_DESIGN_RESEARCH.md](../design/ARCHEUS_V1_DESIGN_RESEARCH.md) |
| Design system | [../design/ARCHEUS_V1_DESIGN_SYSTEM.md](../design/ARCHEUS_V1_DESIGN_SYSTEM.md) |
| Target architecture | [target-architecture.md](target-architecture.md) |
| Domain model | [domain-model.md](domain-model.md) |
| State machines | [state-machines.md](state-machines.md) |
| Resource router | [resource-router.md](resource-router.md) |
| Execution | [execution-architecture.md](execution-architecture.md) |
| Context and knowledge | [context-and-knowledge.md](context-and-knowledge.md) |
| API and realtime | [api-and-realtime.md](api-and-realtime.md) |
| UI architecture | [ui-architecture.md](ui-architecture.md) |
| Migration and gap analysis | [migration-plan.md](migration-plan.md) |
| Testing | [testing-strategy.md](testing-strategy.md) |
| Decisions | [decisions/](decisions/) |
| External research | [../research/external-references.md](../research/external-references.md) |

Source documents (local, gitignored — summarised faithfully here, not committed):
`docs/architecture/reference/Archeus_v1_System_Specification.md`, `Archeus_v1_Implementation_Plan.md`,
`Archeus_v1_Architecture_Design_and_Plan_FIXED.pdf`, `Archeus_v1_Architecture_Designs.pptx`.

---

## 1. Executive summary

Archeus today is a memory and workspace layer around Claude Code / Codex / pi sessions that the
user drives. Archeus V1 becomes a **persistent AI colleague that drives the work**: the user
states outcomes; Archeus turns them into missions, assembles context, plans, asks when policy
says so, routes work across harnesses/accounts/models by the user's priority and allocation,
executes on the user's machine, verifies and reviews, updates a trustworthy picture of the
world, and learns — controllable from desktop, phone and terminal.

The build is a **stdlib-only Python modular monolith ("Archeus Core")** with SQLite as the
source of truth and a transactional event log, a local execution node running harness CLIs
under capability-removal policy, an SSE event stream, and **one TypeScript/React SPA** for
desktop, web and a PWA on phones. It grows beside the current package (strangler); working
capabilities are reused through narrow seams; the legacy app retires only when a capability
checklist passes.

The minimal V1 slice that passes all acceptance scenarios is in §31.2; the release gate in §34.

## 2. Product definition

> **Tell Archeus what you want. It figures out what needs to happen.**

Archeus is a persistent AI operating layer for a person's digital and project world. It
understands current state, history and durable knowledge; turns intent into missions; gathers
relevant context; plans and executes work; coordinates agents and resources; verifies results;
updates state; learns from meaningful feedback; and remains controllable across devices.

The operating loop: **observe → understand → reason → suggest → plan → ask/approve → act →
verify → update state → learn → continue**. Stage-to-module mapping:
[target-architecture.md §6](target-architecture.md).

Principles: the prompt's 22 principles are condensed into eight checkable design rules in
[design research §15](../design/ARCHEUS_V1_DESIGN_RESEARCH.md).

## 3. Current-state findings

Detailed archaeology: [design research §2–8](../design/ARCHEUS_V1_DESIGN_RESEARCH.md) and
[migration-plan.md §2](migration-plan.md). Key facts:

- 91 Python modules (~43k lines), ~16k lines of vanilla web, zero runtime dependencies, Windows
  first, ~1,300 tests with many mutation-verified gates.
- No database: JSON/JSONL files across `~/.claude`, each account's config dir and each project's
  `.archeus/`. No domain event log (the event file is diagnostics).
- ~150 UI-shaped HTTP routes, polling only; jobs are in-process threads; approvals are job gates.
- The strongest coupling: `gui_api._install_bridge` monkeypatches TUI prompt functions so domain
  flows written for the terminal can run inside GUI jobs; the headless model runner and quota
  preflight branch on which UI is active; cancellation reads a thread-local.
- Real, reusable capabilities: multi-account rotation and quota latching, usage polling,
  newest-model following, memory graph + BM25 recall with relation expansion, lessons,
  repository discovery (submodules/worktrees), import-graph extraction, worktree board, provider
  failover proxies, notifications, a platform seam for terminal input, a hex-first palette system
  with contrast tests.
- Gaps against V1: no mission/plan/task objects, no policy engine, no router, no verification,
  no automation beyond scheduled memory refresh and loops, no remote/mobile surface, hook guard
  fails open, pi has no interception point.

## 4. Why the current architecture is insufficient

| V1 requirement | Why today's architecture cannot meet it by extension |
|---|---|
| Missions survive restarts and session rotation | work state lives in thread memory and a markdown file; there is nothing to resume |
| Trustworthy, auditable current state | no transactions, no event log, state reconstructed by polling many files |
| Policy-controlled autonomy | permissions are Claude Code settings the user edits; no per-action evaluation, no approvals bound to actions |
| Explainable routing across accounts | rotation is a sticky threshold with no record of why |
| Multi-device control | loopback-only server, per-run token, no device identity, polling |
| Clients without business logic | domain flows are written against TUI prompts |
| Knowledge that evolves | memory graph has implicit schema, no supersession links, written to two places |

## 5. Target product model

- Mental model and IA: [design research §16–17](../design/ARCHEUS_V1_DESIGN_RESEARCH.md) —
  **Now · Work · World · Control** plus the **Attention** layer and **command bar** (ADR-0014).
- Conversation model: one primary conversation + mission threads, live cards, deterministic
  control verbs (ADR-0006, ADR-0015).
- Presence comes from continuity: since-you-left digest, specific progress, the thread.

## 6. Target domain model

[domain-model.md](domain-model.md). Key choices: current state / history / knowledge kept in
different stores; Principal model (only user devices approve; executions cannot create
missions); Session bound to (harness, account); model is a per-execution attribute; Approvals
bound to action hashes; RouteDecision and PolicyDecision persisted.

## 7. Target technical architecture

[target-architecture.md](target-architecture.md): modular monolith Core (ADR-0001), stdlib only
(ADR-0003), single writer + transactional outbox (ADR-0002), outbox consumers for every side
effect, local in-process execution node with a remote-node contract (ADR-0008), SSE
wake-and-requery (ADR-0009), one SPA (ADR-0011). Core lifecycle: single-instance lock,
discovery file, runs with the GUI closed, optional autostart, sleep → GRACE → reconcile.

## 8. Target data architecture

[target-architecture.md §5](target-architecture.md): `<ARCHEUS_HOME>/archeus.db` (SQLite WAL,
`user_version` migrations, daily + pre-migration backups), content-addressed artifacts,
`run/` for liveness and e-stop. Harness homes and legacy stores are read, not owned (ADR-0019).

## 9. Context architecture

[context-and-knowledge.md §2](context-and-knowledge.md): levels L0–L4 with budget shares,
deterministic retrieval (BM25 reuse + anchors + relation expansion + temporal + explicit pins),
deterministic scoring, stored context packages with reasons, conflicts, gaps and exclusions.

## 10. Knowledge architecture

[context-and-knowledge.md §3–5](context-and-knowledge.md): typed items with provenance, scope,
confidence, validity windows and supersession; EXTRACTED/INFERRED/AMBIGUOUS relations;
promotion pipeline with corroboration; forget with dry-run; SQLite graph via recursive CTEs;
no vector store in V1 (ADR-0012, ADR-0013).

## 11. Mission architecture

- Lifecycle: [state-machines.md §2](state-machines.md). Learning is not a state (`learned_at`).
- **Intent pipeline** (`core/missions/intent.py`):
  1. Deterministic grammar (`application/grammar.py`) recognises control verbs and object
     references (`pause <mission>`, `approve`, `why <x>`, `status`, `stop all`, `remember …`).
     Matched → executed/answered with no model call.
  2. Otherwise a brain call (structured output, schema `intent.v1`) classifies: question /
     new_work / continue_work / feedback / preference / idea, with target refs, ambiguities and
     a confidence.
  3. Ambiguity above threshold or a **conflict with CONFIRMED knowledge** → a Challenge block
     (the user chooses) instead of a mission. Archeus is expected to disagree when evidence
     disagrees (spec principle 15).
  4. new_work → Mission in CREATED with explicit/inferred requirements separated; the mission
     card asks for confirmation unless the autonomy profile allows auto-start for this scope.
- **The brain** (ADR-0006): Core-side structured-output calls through the router (brain is a
  routed consumer with `brain_reserve_pct`), stable prompt prefixes for cache hits, outputs
  validated against JSON schemas in `core/brain/schemas/`, then applied as commands by Core.
  The brain's principal can *propose*; it can never approve. Brain calls are **tool-less
  structured calls** (§31.4): they need the ADR-0021 gate but not P9; until P10 the account is
  chosen by legacy `rotate.elect()` + `quota.reason()`.
- Progress is computed from the task DAG weighted by estimates — never reported by an agent.

## 12. Planning architecture

- Planner (`core/planning/planner.py`) = brain call on a `large` tier model (blast radius: a
  plan error replicates into every task), schema `plan.v1`: tasks with the four-part dispatch
  contract (objective, expected output, allowed action classes/tools, boundaries),
  `depends_on`, `touches[]` globs, `kind`, `capabilities_required`, `min_model_tier`,
  `estimate`, verification per task, approval points, risks, rollback, cost band.
- Validation (deterministic, `dag.py`): acyclic; every `touches` overlap between parallel tasks
  serialised; every task has a verifier or is `human`; action classes known; cost band computed
  from task count × tier × size (bands only).
- Policy pre-evaluation of the whole plan decides `plan_auto_approved` vs `APPROVAL_REQUIRED`
  (state-machines §2) and marks approval points on tasks that will ASK at action time.
- Editing a plan creates a new version; approvals of old versions are SUPERSEDED.
- Replanning receives: previous plan, failing evidence, checkpoints, review verdict; budget 2.

## 13. Policy architecture

Status **DECIDED** (ADR-0007).

**Question answered:** *May Archeus perform this exact action, in this exact context, right now?*

**Inputs:** canonical action `{class, target, argv?, diff_hash?, environment?, cost?}`, actor
principal, mission/task/execution, project/workspace, resource, current state (e.g. mission
paused, e-stop armed).

**Action classes** (closed list in `core/domain/actions.py`): `read`, `web`, `write_repo`,
`exec`, `git_commit`, `git_push`, `deploy`, `external_comm`, `destructive`, `spend`,
`personal_data`, `install`, `credential`.

**Evaluation** (`core/policy/engine.py`), pure and deterministic:

```python
def evaluate(action, ctx) -> PolicyDecision:
    if estop_armed():                       return deny("emergency stop armed")
    rules = matching_rules(action, ctx)     # all scopes GLOBAL→USER→WORKSPACE→PROJECT→MISSION→TASK→ACTION
    for r in rules_by_scope_desc(rules):    # most specific first...
        if locked_above(r, rules):          #   ...but a locked rule at a broader scope cannot be loosened
            continue
    decision = strictest(                   # combine: DENY > ASK > ALLOW_WITHIN_BOUNDARY > ALLOW
        effective(rules))                   # effective = most specific non-shadowed rule per class,
                                            # locked broader rules always included
    if decision is ASK and one_shot_allow_matches(action):  return allow(consume=approval)
    if decision is ALLOW_WITHIN_BOUNDARY and not inside(action, boundary): return ask_or_deny(...)
    return record(decision, rules, reason=render(rules))
```

- DENY is always locked. A broader locked ASK cannot be turned into ALLOW by a project rule.
- `unclassified` exec actions (shell pipelines, eval, decoding into a shell) are evaluated as the
  strictest class active for the task.
- **Profiles** are named rule bundles applied at a scope: *Careful* (everything but read/web =
  ASK), *Standard* (read/web ALLOW; write_repo/exec ALLOW_WITHIN_BOUNDARY of the project worktree;
  git_commit on task branches ALLOW; merge to main, push, install, spend > band ASK; deploy,
  external_comm ASK; destructive on prod DENY), *Autonomous* (Standard + merge/push to non-default
  branches ALLOW). Default profile at first run: **Standard**.
- Spec examples as rules: web research ALLOW (GLOBAL); modify project repository
  ALLOW_WITHIN_BOUNDARY (PROJECT, paths = project roots, branches = `archeus/*`); production
  deployment ASK (GLOBAL, `environment: prod`, locked); external communication ASK (GLOBAL);
  destructive production operation DENY (GLOBAL, locked).
- **Enforcement points:** (1) Core before its own actions (merge, push, deploy, notifications to
  third parties); (2) the execution environment (capability removal —
  [execution-architecture.md §2](execution-architecture.md)); (3) the per-tool hook (Claude Code)
  or sandbox (Codex). Harnesses with `enforcement: none` only receive all-ALLOW tasks.
- **Audit:** every ASK/DENY and every mission-scoped ALLOW produces a PolicyDecision; policies
  are versioned and every change is an event; `POST /v1/policies/simulate` answers "what would
  happen if…" without acting.

## 14. Resource Router

[resource-router.md](resource-router.md) (ADR-0005): capability → enforcement → policy →
restrictions → health → allocation (ceiling semantics, stale-usage penalty, budgets when the
window is unknown, brain reserve) → ordering (affinity, preference, priority, tier fit, health,
cost, latency) → persisted, replayable, explainable decision → fallback only as policy allows.

## 15. Execution architecture

[execution-architecture.md](execution-architecture.md): INTENT-before-spawn, process registry
with pid + create_time, boot reconciliation, cooperative pause, stop by verified pid, ASK
mid-execution via hook halt + resume with a one-shot allow, Core-derived checkpoints, worktrees
at node-computed paths, Core-only merge/push, e-stop with and without Core.

## 16. Verification

[execution-architecture.md §8](execution-architecture.md) and
[state-machines.md §6–7](state-machines.md): verifier per artifact kind, GenericVerifier = human
acceptance, verification ERROR ≠ FAILED, review on an independent resource when possible
(`independent=false` recorded otherwise). Only verified + reviewed missions become COMPLETED.

## 17. Automation

Status **DECIDED** (ADR-0020). Model in [domain-model.md §9.4](domain-model.md), lifecycle in
[state-machines.md §8](state-machines.md).

- Triggers: `event` (type + subject pattern + payload predicate, e.g.
  `repository.model_added where project=Payments and path !~ tests/`), `schedule` (cron subset:
  minute hour dom month dow, evaluated in Core's scheduler), `condition` (a query evaluated on a
  schedule, e.g. "any mission blocked > 24 h"), `state` (entity enters a state).
- Pipeline: event → matcher (outbox consumer) → claim run (single transaction) → conditions →
  policy (template action classes under the automation's overlay) → mission from template →
  normal mission loop → verify → update → notify.
- Guards: cause-chain depth cap (escalate), rate limit, suspension after repeated escalation,
  simulation against the last 30 days before enabling.
- First templates (from the implementation plan): document a new model file; update project
  state after a mission completes (built-in, not user-visible); notify on blocked; reroute on
  account limit (built-in router behaviour); refresh architecture on repository change; scheduled
  research briefing; plus migrated legacy loops and auto-memory refresh.

## 18. Event system

[api-and-realtime.md §3](api-and-realtime.md) and [state-machines.md §14](state-machines.md):
events written in the same transaction as state; integer `seq` cursor; typed registry in one
file; consumers with cursors and idempotent effects; retention with 410 resync; events describe
facts, consumers decide meaning.

## 19. Repository understanding

[context-and-knowledge.md §6](context-and-knowledge.md): registration via `repos.find_git_repos`,
cheap HEAD check, deterministic pass (languages, manifests, docs, agent config, import graph via
`connections.build_hierarchy`, commands) with content-hash caches, optional model pass,
inspection diffs, architecture constraints with drift detection and a three-way resolution.

## 20. External source understanding

REFERENCE knowledge items with URL, inspected_at, revision, observations, design area,
confidence, adopted/adapted/rejected/deferred — the format used for this plan's own research in
[../research/external-references.md](../research/external-references.md).

## 21. GUI architecture

[ui-architecture.md](ui-architecture.md): one SPA, one navigation table, surfaces Now / Work /
World / Control + Attention + command bar, canonical inspector with a Why tab, approval contract,
2D graph view, repo UI gates carried over.

## 22. Mobile architecture

PWA of the same SPA over a user-operated HTTPS tunnel (Tailscale Serve recommended), device
pairing with one-time codes, scoped revocable tokens, ntfy push with deep links, step-up PIN for
destructive approvals, bottom-tab adaptation. Status **PROPOSED** (ADR-0010); decided parts:
no native app in V1, no Mac or Apple developer account required.

## 23. TUI architecture

[ui-architecture.md §6](ui-architecture.md): thin CLI in the slice (status, approve, pause,
route why, estop, pair); full TUI on the API later in V1 reusing `term.py` and `render.py`;
glyphs from the design system; legacy TUI until retirement.

## 24. Spatial visualization

[design research §26](../design/ARCHEUS_V1_DESIGN_RESEARCH.md) and
[ui-architecture.md §5](ui-architecture.md): 2D fine-line graph, every visual variable mapped to
a domain fact, energy only for live executions, list equivalent, 3D optional later (ADR-0016).

## 25. Design system

[../design/ARCHEUS_V1_DESIGN_SYSTEM.md](../design/ARCHEUS_V1_DESIGN_SYSTEM.md): quiet
instrument, fixed state colours with glyphs, one signature element (the thread), tokens from one
table for CSS/TS/ANSI, accessibility floors gated (ADR-0017).

## 26. API / realtime

[api-and-realtime.md](api-and-realtime.md): commands/queries, one route table generating docs
and the TS client, idempotency keys, typed errors, SSE ids-only with replay, separate stream
pool, leader-tab stream sharing.

## 27. Security

| Concern | Design |
|---|---|
| Authentication | device tokens (typed `dev_`/`node_`/`hook_`; token prefixes never reuse an entity-id prefix; 256-bit, hashed at rest, `hmac.compare_digest` on bytes); local token in `run/local-token` (POSIX `0600`, Core refuses looser modes; on Windows the
default home inherits the user-profile ACL and a home outside it gets a warning — DPAPI is the
upgrade path); pairing with 2-minute single-use rate-limited codes shown only in a local session |
| Authorization | Principal scopes (observe/control/approve/admin; propose for brain; report/checkpoint/request_approval for executions); route table declares the required scope per route |
| Transport | loopback by default; remote only via HTTPS tunnel; Host/Origin allowlist includes paired hostnames only; fetch-metadata allowlist for browsers; never trust source address; tokens never in query strings |
| Web | strict CSP `script-src 'self'`, no inline handlers; agent output rendered as text or sanitised markdown; approval cards show canonical actions, never model prose alone |
| Policy enforcement | capability removal first (no push credentials in executions, sandbox flags, tool allowlists), fail-closed hook for Archeus executions, Core-only merge/push/deploy/external_comm |
| Credential isolation | accounts are node-bound; Core stores metadata and usage only; API keys at rest via DPAPI (`ctypes`) on Windows, 0600 files on POSIX; env scrubbed per execution (`config.account_env`) |
| Destructive actions | `destructive` class; DENY on prod by default (locked); ASK elsewhere with step-up |
| Approvals | bound to hash(action + policy version + plan version); single-use; expiring; superseded on replan; idempotent decisions |
| Remote access | opt-in; documented threat model: whoever holds an `approve` device can approve anything policy lets be asked; revoke closes streams immediately |
| Event security | events carry scope; SSE filters by device scope; payloads small and secret-free; artifacts referenced by hash, served only with a scoped token |
| E-stop | Core-side (all executions stop, automations disabled, routing refused) and Core-less (STOP sentinel + `archeus estop`) |
| Supply chain | Core stdlib-only; SPA dependencies pinned with lockfile, built in CI, audited (`npm audit` gate); `git clone` of anything uses `proc.remote_url_ok` + `--` (existing rule) |
| Prompt injection | fetched content, meeting notes and agent output are data: never parsed as commands; control verbs only from user principals; brain outputs validated against schemas before any command |

## 28. Observability

Everything is reconstructable from the event log plus decision records:

| Question | Answered by |
|---|---|
| What happened / what changed | events filtered by subject/time; mission Timeline |
| Why did it happen | PolicyDecision, RouteDecision, context package reasons, plan version, cause_chain |
| What resource was selected | RouteDecision (+ input snapshot for replay) |
| What failed / what was retried | execution exit reasons, attempts, three-strikes records, verification outputs |
| Model usage and cost | UsageLedger (per execution/mission/account/model), UsageSnapshots |
| Context size | context package token totals per level |
| Hand-offs | checkpoints with triggers |
| Automations | AutomationRun rows with skip/escalate reasons |
| What the user needs to do | Attention query |

Metrics derived nightly into a `metrics_daily` table (missions completed/failed, median time to
complete, approvals per mission, fallback rate, verification failure rate, cost per mission
band, context tokens per task kind) and shown in Control → About → Health. Diagnostics (Core
crashes, consumer errors) go to `<ARCHEUS_HOME>/logs/core.log` with rotation; the `archeus doctor`
command checks DB integrity, consumer lag, stuck executions, hook installation.

## 29. Migration

[migration-plan.md](migration-plan.md): strangler, subsystem-by-subsystem classification, P0.5
seams, data importers, ownership table, retirement checklist, rollback.

## 30. Testing

[testing-strategy.md](testing-strategy.md): judge-first acceptance suite with a traceability
table over all four acceptance sources, contract tests for adapters, property tests for router
and policy, design gates, mutation verification and floors.

## 31. Implementation phases

Sequencing changes from the source plan (0–24), each justified:

| Change | Why |
|---|---|
| **P0.5 Seams** inserted, deliberately narrow | the reused modules are already UI-free *at import*; the coupling is at call time (the headless runner reaches `gui_api`, whose import runs `_install_bridge()`), plus two process-control gaps and legacy hooks that would fire inside V1 executions. Restructuring retiring code has no V1 value |
| Judge + fake harness + frozen adapter contract **in P1** | migration-kit rule: no judge, no exit condition; everything after P1 is measured against it |
| Security basics (principals, tokens, audit) **in P2** instead of P20 | identity and audit are properties of every row; retrofitting them is a rewrite |
| **P3.5 API + SSE + walking skeleton** added | a disposable end-to-end run (the migration kit's substitute for a bakeoff in redesigns) that makes every later phase visible; skeleton uses the fake harness only |
| **Policy (P9) gates real tool-using execution** | no real agent with tools may run before the policy engine and capability removal exist; enforced in code (the adapter registry refuses real adapters while policy is the P1 stub). Tool-less structured calls are a separate class (§31.4) |
| Brain as structured-output calls (P7), not an MCP server | P7 would otherwise depend on the execution stack (P11); until P10 the account comes from legacy `rotate.elect()` + `quota.reason()` (§31.4) |
| **Provider-terms gate (ADR-0021) moved** from P0 to *immediately before the first real headless model call* | P0.5–P3.5 make no real model call; the architecture supports API-key accounts regardless of the answer |
| P20 = hardening, P21 = observability *views* | the mechanisms exist from P2 (events, decisions); these phases add breaker drills, secrets review, trace UI and metrics |

### 31.1 Phase table

Every phase ends at a gate: evidence produced, acceptance met, sign-off = starting the next
phase. Legacy tests stay green in every phase. "Sx passes" in a phase means the judge functions
tagged with that phase pass; "part" means some of the scenario's functions do, per the
per-function tagging rule in [testing-strategy.md §1.1](testing-strategy.md).

**P0 — Archaeology, feasibility and research** · *done*
- Objective: understand the current product and references; decide whether V1 proceeds.
- Deliverables: this document set; ADRs; external references; the readiness review and its
  corrections (Appendix D).
- Gate: user sign-off on this plan (given). The provider-terms question (ADR-0021) is **not** a
  P0 gate any more: it gates the first real headless model call (§31.4).
- Risk: using subscription accounts headlessly in a way the provider does not permit → nothing
  assumes it is permitted; if it is not, the same architecture runs on API-key/provider accounts.

**P0.5 — Seams (legacy edits only; `archeus/` does not exist yet)**
- Depends: P0. Seams (detail and exact contracts in [migration-plan.md §3](migration-plan.md)):
  1. **Headless runner** — new UI-free module `claude_sessions/llmcall.py` holding the process
     core of `gui_api._run_cancellable` (spawn with the prompt on stdin, cancel via an `Event`,
     `proc.kill_tree` on cancel/timeout, capture, on non-zero exit `quota.note_failure` +
     `events.record` + the error text) and the argument builder from `memory._claude_stdin`
     (`HEADLESS_MARK`, `--max-turns`, disallowed write tools, budget args, provider env).
     `_run_cancellable` and `_claude_stdin` become thin wrappers with unchanged behaviour
     (preflight, `_JOBCTX` cancel, foreground progress UI, `last_call_error`, `why_failed`).
  2. **Process control** — additive functions in `proc`: `process_create_time(pid)`,
     `kill_pid_tree(pid, create_time)` (refuses when the create time does not match), and a
     `stdin_path=` parameter on `spawn_detached` (today it forces `stdin=DEVNULL`, and headless
     `claude -p` takes its prompt on stdin).
  3. **Hook environment guard** — `recall_hook`, `worklog_hook`, `memdirty_hook` return
     immediately when `ARCHEUS_EXECUTION_ID` is set; `limit_hook` still calls
     `quota.note_limit` (the shared latch is wanted) but skips `rotate.offer` (which could open a
     successor session for a V1 execution). All other behaviour unchanged when the variable is
     absent.
- Not in P0.5 (moved): usage-snapshot seam → P10 preparation; `build_launch_command`
  extraction → P11 preparation; `cli.py` dispatch → P3.5. **Dropped:** splitting `connections`
  (it is already importable without UI; a split risks the import-by-value bug class) and
  `quota.assess` (`worst_window` reports unknown usage as 0, which is the wrong primitive for
  the router).
- Tests: existing suite green; unit tests per seam; mutation checks (legacy wrappers must route
  through `llmcall`; each hook must skip under the variable and only then).
- Acceptance: importing `claude_sessions.llmcall` and `claude_sessions.proc` in a fresh
  interpreter loads none of `claude_sessions.ui`, `.gui_api`, `.main`, `.gui` (an import-graph
  test asserts it); all four hook scripts behave identically when `ARCHEUS_EXECUTION_ID` is
  absent.

**P1 — Domain model, contracts and the judge**
- Depends: P0.5. New:
  - packaging: `archeus/__init__.py`; `pyproject.toml` `packages` gains `archeus` (and its
    subpackages); `tests/test_packaging.py` updated accordingly.
  - `archeus/core/domain/*` (ids, states table, entities, action classes, events registry).
  - `archeus/infra/paths.py` — the **`ARCHEUS_HOME` resolver**
    ([target-architecture.md §5.1](target-architecture.md)), a function, never an import-time
    constant.
  - `archeus/core/ports.py` — interfaces for Policy, Router, Brain, Verifier, Review and Node,
    plus **stubs**: allow-all policy (`is_stub = True`), fixed-candidate router, scripted brain,
    auto-pass verifier, auto-accept review. The adapter registry **refuses any non-fake adapter
    while the policy implementation is a stub** — the P9 gate as code, not convention.
  - `archeus/harnesses/base.py` — the adapter contract, frozen, including the process I/O
    contract ([execution-architecture.md §3.1](execution-architecture.md)): stdin file, JSONL
    stream file, spawning marker. `archeus/harnesses/fake.py` — the fake harness is a **real
    subprocess** (a Python script driven by a scenario file) so registry, stream-tailing and
    reconciliation paths are exercised from the start.
  - `tests/v1/judge/` — the `CoreClient` contract and every scenario written against it, each
    marked `xfail` with the phase that will make it pass
    ([testing-strategy.md §1.1](testing-strategy.md)); `test_traceability.py`;
    `test_skeleton_vertical_slice.py` (xfail until P3.5); `tests/v1/unit/test_state_tables.py`.
- Tests: invariants, serialisation, state-table ↔ diagram parity, fake-harness subprocess
  scripts, stub guard (registering a real adapter with the stub policy raises).
- Acceptance: every entity of domain-model.md exists as a dataclass with validation and the
  **minimal fields the judge scenarios need** (other fields arrive with the phase that uses
  them); the judge runs and reports every scenario as xfail with a phase tag; the fake harness
  runs as a subprocess against the frozen contract.

**P2 — Persistence, event log, identity basics**
- Depends: P1. New: `infra/db` (connection, writer thread with futures + idempotency, migrations
  `0001_init.sql`, backup), `infra/eventlog` (outbox, consumer cursors/effects, retention),
  `infra/artifacts`, Principal/Device/token tables, audit fields, and the **transactional
  transition primitive** (`Tx.transition`): check `expected_version`, check the edge against the
  P1 state table, assign the state, bump `version`, append `<machine>.state_changed` with a
  required reason — one transaction. It refuses a guarded edge without a matching P3 transition
  proof; it is persistence, not the lifecycle layer.
- Tests: crash-safety (kill between write and consumer), idempotent re-delivery, optimistic
  concurrency conflicts, migration + backup, writer throughput (≥ 500 commands/s on the dev box),
  startup refuses SQLite older than 3.31 and the schema uses neither `RETURNING` nor `STRICT`
  (the dev box has 3.37.2; older Linux builds exist).
- Acceptance: G1 and G4 judge tests pass at the persistence level.
- Risks: SQLite contention → single writer by design; readers `query_only`.

**P3 — State machines**
- Depends: P2. New: the application-level `transition()` built on P2's primitive — guarded
  transition semantics, action semantics, policy interaction and lifecycle orchestration — plus
  guards and all machines of state-machines.md. The P2 primitive stays the only writer of
  `state` and never grows guards, policy or orchestration of its own. Guards that
  consult policy, router or verification (e.g. `plan_auto_approved`) call the P1 ports, so they
  run against the stubs until P9/P10/P13 replace them.
- Tests: every edge allowed, every non-edge rejected (generated), guards pure.
- Acceptance: illegal transitions return 422 with machine/from/to.
- As built: guards in `core/domain/guards.py`, the transition in `core/application/lifecycle.py`,
  mission actions (`advance`, `pause`, `resume`, `cancel`, `request_changes`, `accept`, `fire`)
  in `commands.Missions` (state-machines §2 "Orchestration").
- **P3 proves the lifecycle semantics, not a production lifecycle.** No new tables: the guard
  snapshot is a `facts(tx, row)` seam, and in production it has no active plan, so every guard
  that needs one refuses (fail closed) and a mission cannot pass `all_tasks_done`; tests script
  the snapshot. **Deferred, deliberately open:** which phase persists Plan, Task, Verification
  and success criteria (P3.5's skeleton needs Task at the latest) — until then no real facts.
  *Resolved in P3.5:* the walking skeleton persists all four and `persisted_facts` reads them.
- P2 stays generic: `Tx.transition` gained `proof=` (a generic `states.TransitionProof`,
  checked against the P1 table) and `fields=` (other entity fields in the same row write).
  P2 owns no guard definition and no mission behaviour (state-machines §0, tested by a scan of
  `archeus/infra/`). Mission gained `max_replans` and `held_from`.
- P3 acceptance is carried by the in-process contract tests (`422 invalid_transition` naming
  machine/from/to, `422 guard_failed`); no judge scenario is tagged P3, and none was invented.
- Still deferred: who may fire which trigger (P9; P3 decides legality only), the persisted
  Approval machine (P9), `KnowledgeItem.body` vs the row's `body` (the phase that persists
  knowledge; the collision test stays).

**P3.5 — API, SSE, walking skeleton**
- Depends: P3. New: `api/server.py` (separate request and stream pools), `api/routes.py`,
  `api/sse.py`, `api/auth.py` (Host/Origin allowlist, CSP, **local launch-code bootstrap** —
  [api-and-realtime.md §5.1](api-and-realtime.md)), `cli/main.py` (`core`, `status`), Core
  lifecycle (single-instance lock and discovery file under `ARCHEUS_HOME`), the HTTP binding of
  `CoreClient`, generated API doc + TS client, a minimal **local node** — the Core-hosted
  engine thread, the existing adapter registry and process I/O files, and a boot reconciliation
  sweep over the database (p3.5b-design-gate.md §18.1; the process registry, live stream
  tailing and adoption are P11's, the execution stream route P16's; real adapters, worktrees
  and `archeus estop` arrive in P11), and the minimal SPA (Now + Work lists) with its Node build
  and CI job ([ui-architecture.md §2](ui-architecture.md)).
- Legacy edit: `claude_sessions/cli.py` dispatches the reserved V1 verbs (`core`, `status`,
  `approve`, `pause`, `route`, `estop`, `pair`) to `archeus.cli.main` with a lazy import placed
  **after** the statusline fast path; every existing verb keeps its current route.
- Flow: `CoreClient.create_mission` (a command; no intent parsing, no brain) → stub brain plan →
  stub policy auto-approves → task → fake execution subprocess (JSONL stream) → stub verification
  and review → COMPLETED; every transition observed over SSE and rendered by the SPA.
- Tests: SSE replay with Last-Event-ID, 410 resync, pool isolation (streams cannot starve
  commands), CSP headers, launch-code single use and expiry, generated artefacts fresh, Core
  killed mid-execution → restart → the fake execution is adopted or reconciled.
- Acceptance: **`tests/v1/judge/test_skeleton_vertical_slice.py` passes** (it is *not* S1: S1
  needs the real brain, policy, router, verification and review and stays xfail until P13);
  skeleton demo recorded.
- **As built — P3.5a (the in-process walking skeleton) and P3.5b (the service).** P3.5 was
  split: the vertical slice first, in process; then P3.5b, designed and decided in
  [p3.5b-design-gate.md](p3.5b-design-gate.md), made it reachable from outside the Core
  process (the P3.5b bullet at the end of this entry). The notes below are P3.5a's.
  - Durable work: migration `0002_work.sql` persists **Plan, Task, Execution, Verification,
    Review** (the P1 entities, with minimal fields added: `Mission.success_criteria`,
    `Plan.summary`/`estimated_cost`, `Task.failure_class`, the Execution's harness, pid,
    creation time and end, `Verification.plan_id`/`criterion`, `Review.plan_id`). No new
    entity, no new machine.
  - Commands: `core/application/work.py` (`Work`) — propose a plan and decide it, ready and
    dispatch tasks, record a spawn, an exit, a reconciliation, a task's checks, a mission's
    criteria and a review. Each is one writer transaction; mission moves go through
    `commands.Missions`, every other move through `lifecycle.fire`. `commands.persisted_facts`
    now reads the guard snapshot from these rows (a verification counts only for the plan it
    ran under).
  - Engine: `core/engine.py` runs one mission step by step (stub steps to REASONING → brain
    plan → plan gate → dispatch → fake execution → task checks → mission criteria → review);
    side effects happen between commands, never inside one. It will split into
    `planning.planner`, `execution.manager` and `verification` when those phases arrive.
  - Stubs (`core/ports.py`): `FixedPolicy` (ALLOW/ASK/DENY), `FixedPlanBrain`,
    `ScriptedVerifier`, `ScriptedReview`; the resource seam is the P1 `FixedCandidateRouter`
    through `AdapterRegistry` (a task never names a harness).
  - Policy is consulted through the port, never by actor kind. ASK → APPROVAL_REQUIRED (a
    human `approve`). DENY → `propose_plan` / `dispatch_task` refuse with `PolicyDenied` before
    writing anything: no plan, task, execution or approval, mission state unchanged; `advance`
    never answers a DENY with `plan_needs_approval`. In EXECUTING the existing `unrecoverable`
    edge ends a mission whose policy turned to DENY.
  - `max_replans` = replans allowed after the initial plan; the budget is judged on the plan
    being replaced, before the brain is asked for a new one.
  - Restart: an execution nobody is watching is reconciled — its process killed by pid +
    creation time, the attempt ended ABANDONED (never spawned) or LOST → ENDED_KILLED, and
    the task retried with a new execution. Adoption of a live process is P11's.
  - The judge's `InProcessClient` pumps the engine from `_idle()`; `test_skeleton_vertical_
    slice.py` passes in process. Tests: `tests/v1/integration/test_skeleton.py` (real child
    processes killed at exact points for the restart cases).
  - **Checkpoint decisions** (no state machine was changed for any of them):
    (1) *accepted* — Plan has no declared edges and stays DRAFT: the versioned strategy
    attached to the mission, which owns lifecycle progression; (2) *accepted* — Review
    REJECTED is a review result, not a mission move; the mission stays in REVIEWING until an
    explicit `request_changes` or a human's own accepting review (`work.record_review`, which
    `accept` requires since the third checkpoint), and never completes from a rejection; (3) *fixed* —
    the replan budget was judged on the newly proposed plan (one replan too few); it is now
    judged on the plan in force, so `max_replans` counts replans after the initial plan;
    (4) *fixed* — DENY no longer becomes APPROVAL_REQUIRED (see above); (5) *deferred to P9* —
    a decision taken at automatic plan approval is not bound to an action hash or policy
    version, so a policy that turns to ASK before dispatch is not asked again, and a denial
    leaves no durable PolicyDecision row (only the typed error) — so driving a denied mission
    again repeats its reasoning (the brain is asked again) until P9 persists decisions;
    (6) *deferred to P10* — the
    auto-approve ceiling is the fixed P3.5 fixture `AUTO_APPROVE_CEILING = 'medium'`, not the
    mission's resource preferences.
  - **Lifecycle integrity (second checkpoint), P3 changes made explicit:** `plan_needs_approval`
    is now a guarded edge of the P1 table (`states._GUARDED`, guard in `guards.py`): a newer
    plan, no DENY, something to ask. Both plan-decision guards refuse the plan recorded in the
    new `Mission.decided_plan_version`, so neither `advance` nor a trigger fired by name can
    re-decide the plan a REPLANNING mission is replacing (the same holds for PLANNING after
    `request_changes`). `Missions._fire` is the single path for mission moves; `advance` lost
    its P3.5 DENY special case because the guard now carries that rule.
  - **Adversarial lifecycle review (third checkpoint)** found four direct-call bypasses the
    engine never takes, each proven by a probe and now refused: (1) REVIEWING → COMPLETED by
    `accepted` with no review → `accepted` is a guarded edge (an accepting review of the plan
    in force); (2) `unblock` + `redispatch` from a hold before any plan → EXECUTING with no
    plan → `redispatch` is guarded by `held_from`; (3) `verification_failed` with nothing
    failed → guarded (and `advance` lost the private copy of that condition, so every exit
    it takes is a table guard); (4) `dispatch_task` of a READY task from a superseded plan →
    refused. The three new guards are P3 table changes (`states._GUARDED`, `guards.py`,
    `MissionFacts.review`). Remaining unguarded mission edges are legal by name and lead
    nowhere a guard protects (`approve` only from APPROVAL_REQUIRED, which only a decided plan
    reaches); who may fire them is P9.
  - **P3.5b (the service), as built.** `archeus/api/` (one route table with request and
    response schemas, the `ThreadingHTTPServer` with separate request and stream pools, SSE,
    device-token authentication with coarse route scopes, the Host / fetch-metadata allowlists
    and security headers, in-memory launch codes), `archeus/core/runtime.py` (lock → database →
    local token → engine thread → HTTP → `core.json`, stopped in reverse; one engine, parked per
    mission version, lost races skipped, any other failure exits 3), `archeus/infra/discovery.py`
    (`core.lock`, `core.json`, `local-token`), `archeus/cli/main.py` (`core`, `status`, five
    deferred verbs), `Engine.reconcile_orphans()` (the boot sweep, over the one `_reconcile`),
    the writer's commit notification, `device.state_changed`, the `register_device` /
    `revoke_device` commands, the HTTP judge binding (`tests/v1/judge/http.py`, every scenario
    on both bindings), the SPA in `clients/app/` built into the wheel, and the generated
    `api-reference.md` and `generated.ts` (`tools/gen_api_docs.py`). No real model call; the
    registry, adoption, live tailing, e-stop, pairing, approvals and routing stay in P9–P16.

**P4 — World model and repository inspection**
- Depends: P3.5. New: `world/projects.py`, `world/inspection.py` (reusing `repos`,
  `connections`), `world/drift.py`, `world/digest.py`; architecture constraints.
- Tests: fixture repos (Python, TS, submodule, worktree), drift positive/negative per
  constraint kind, cheap HEAD check.
- The optional model pass of inspection is a tool-less structured call (§31.4): disabled until
  the ADR-0021 gate is passed; the deterministic pass alone must satisfy the acceptance.
- Acceptance: S7, S13 (deterministic part), S14 pass.

**P5 — Context engine**
- Depends: P4. New: `context/*`, `infra/search/bm25.py` (reusing `recall`).
- Tests: budgeting per level, reasons present for every item, superseded excluded, stale
  labelled, conflicts detected, deterministic ordering.
- Acceptance: G2 passes; context preview endpoint.

**P6 — Knowledge and learning**
- Depends: P5. New: `knowledge/*` (items, relations, promote, forget, ingest), learning pass
  consumer; meeting import. Decision-candidate extraction from notes is a tool-less structured
  call (§31.4); tests use the scripted brain.
- Tests: supersession chains, corroboration gating, forget dry-run, idempotent import.
- Acceptance: S8, S9 pass.

**P7 — Intent, brain, mission engine**
- Depends: P6. New: `application/grammar.py`, `missions/intent.py`, `brain/calls.py` (on the
  P0.5 `llmcall` runner; account from legacy `rotate.elect()` + `quota.reason()` until P10),
  schemas, challenge logic, mission service. **The ADR-0021 gate must be passed before the first
  real brain call**; until then P7 runs on the scripted brain and recorded fixtures.
- Tests: grammar table tests (every control verb, no model call), schema validation failures
  handled (retry once, then ask the user), challenge on conflicting knowledge.
- Acceptance: S15, SP3 pass (scripted brain); S1's intent-to-plan function passes on recorded
  brain responses (S1 as a whole stays xfail until P13).

**P8 — Plan engine**
- Depends: P7. New: `planning/*`.
- Tests: DAG validation, serialisation of overlapping `touches`, versioning, supersession of
  approvals, cost bands.
- Acceptance: plans for all judge scenarios validate; S6 replan path passes with the fake harness.

**P9 — Policy and autonomy**
- Depends: P8. New: `policy/*` (engine, rules, profiles, approvals, simulate), hook evaluate
  endpoint, step-up.
- Tests: precedence/lock property tests, approval replay/expiry/supersede/idempotency,
  unclassified exec, e-stop deny.
- Acceptance: S5, G6 (policy part) pass. **Gate:** real adapters may be enabled after this.

**P10 — Resource Router**
- Depends: P9. Preparation seam (legacy, additive): a public `usage` helper returning
  `(windows, observed_at, status)` per account from the existing poller state and
  `_extract_windows`, so "unknown" is distinguishable from 0%. New: `routing/*`; UsageSnapshot
  consumer (reusing `usage.fetch_usage`), ledger.
- Tests: property tests (never exceed ceiling at start, DENY never selected, replay equality),
  fake usage feed scenarios.
- Acceptance: S3, S4 (routing part), S12 pass.

**P11 — Execution orchestrator**
- Depends: P10. Preparation seam (legacy): move `main.build_launch_command` and its helpers
  into a UI-free module re-exported from `main` (today `main` imports the TUI), used by the
  interactive-attach path. New: `execution/manager.py`, `node/*` completed (worktrees, estop,
  real-adapter supervision), `harnesses/claude_code` (headless + policy hook + pressure),
  `harnesses/codex`; the real policy implementation replaces the stub, which unlocks real
  adapters in the registry.
- Tests: contract tests on recorded streams; reconciliation with real child processes (a Python
  stub CLI); PID-reuse safety; cooperative pause; stop; e-stop without Core.
- Acceptance: S1 and S5 pass against the **real** Claude Code adapter in the opt-in contract
  suite; G5, G7 pass.
- Risks: CLI flag drift → adapters pin tested versions and report `MISCONFIGURED` on mismatch.

**P12 — Session and context continuity**
- Depends: P11. New: `execution/checkpoint.py`, `execution/handoff.py`.
- Tests: pressure from recorded usage, PreCompact backstop, account-change hand-off creates a new
  session, mission state unchanged.
- Acceptance: S2, S4 (hand-off part) pass.

**P13 — Verification and review**
- Depends: P12. New: `verification/*`, integration (merge-back) machine.
- Tests: verifier ERROR vs FAILED, human acceptance path, independent flag, merge conflict →
  BLOCKED + follow-up task.
- Acceptance: S6 passes end-to-end; S1 completes only after verification + review.

**P14 — Event bus and automation**
- Depends: P13. New: `automation/*`, templates, simulation.
- Tests: loop guard, claim-and-advance under concurrent ticks, schedule parsing, suspension.
- Acceptance: S10, S10b pass.

**P15 — Presence, pairing, remote, mobile**
- Depends: P14 (and P3.5). New: pairing routes, scope enforcement for *paired* devices (local
  credentials' route scopes, revocation and token-in-query rejection are P3.5b's), remote host
  allowlist, ntfy notifier, PWA manifest + service worker (offline shell only), mobile layouts.
- Tests: pairing expiry/rate limits, a paired device's revoked stream closes, PWA install on
  Android/iOS (manual checklist), ntfy payload contains no secrets.
- Acceptance: S11, S14 (cross-device) pass.

**P16 — GUI information architecture**
- Depends: P15. New: full SPA surfaces, tokens pipeline, design gates, Qt shell attach.
- Tests: E2E per surface, contrast, keyframes, dead-space/overflow audit, accessibility checks
  (axe-core in Playwright), floors.
- Acceptance: G3 (GUI part); Apple-skill five-lens review passes with no Critical findings.

**P17 — TUI**
- Depends: P16 (shares nav table and presentation table). New: `cli/tui/*`.
- Tests: scripted keys per screen; monochrome rendering; parity with nav table.
- Acceptance: G3 (TUI part).

**P18 — Spatial visualization**
- Depends: P16. New: `clients/app/src/graph/*`, `/v1/world/graph`.
- Tests: encoding table ↔ renderer parity test; keyboard traversal; 1,000-node budget; reduced
  motion.
- Acceptance: drill world → project → mission → execution; list equivalent.

**P19 — Client unification**
- Depends: P16–P18. Work: remove any logic that crept into clients; generated client everywhere.
- Test: the implementation plan's unification scenario (create on desktop → observe on mobile →
  approve on mobile → execute on PC → review on desktop → inspect on TUI).
- Acceptance: G3 fully passes.

**P20 — Security and trust hardening**
- Depends: P19. Work: breaker drills, e-stop drills, secrets review (DPAPI path), threat-model
  review of remote access, dependency audit, fuzzing of the command API and hook canonicaliser.
- Acceptance: G6 fully passes; no High findings open.

**P21 — Observability views**
- Depends: P20. New: trace view per mission, metrics_daily, Health page, `archeus doctor`.
- Acceptance: every question in §28 answerable from the UI.

**P22 — Legacy migration**
- Depends: P21. New: `legacy/importers.py`, onboarding import flow, ownership cutover.
- Tests: fixture legacy homes (multi-account, codex, pi), idempotency, counts.
- Acceptance: G8 passes; retirement checklist (migration-plan §6) evaluated.

**P23 — Acceptance program**
- Depends: P22. Run the whole judge + E2E + contract (real harness) + manual mobile checklist on
  Windows (primary), macOS, Linux.
- Acceptance: all traceability rows green.

**P24 — V1 release gate** — §34.

### 31.2 Minimal V1 slice (what "V1 exists" requires)

Core + SQLite/outbox/SSE · structured-output brain · mission/plan/task · policy + approvals +
fail-closed hook · router with ≥ 2 Claude accounts (ceiling, affinity, fallback modes) · Claude
Code + fake adapters · checkpoint hand-off · CodeVerifier + human acceptance · bounded replan ·
repository re-inspection with drift · file-import knowledge (meetings) · lessons with
supersession · event + schedule automations with loop guard · since-you-left digest · SPA with
Now/Work/World/Control/Attention as lists · PWA over Tailscale Serve · ntfy · thin CLI.
**V1 release additionally requires** the Codex adapter (provider neutrality proven with a second
real harness) and the full TUI.

**Deferred past V1:** remote execution nodes, pi/generic-CLI adapters, 3D spatial mode, Web
Push, FTS5, vector search, EMA reinforcement and contradiction edges, Archeus-as-MCP-server,
multi-user workspaces, WebAuthn step-up.

### 31.3 Dependency graph

```mermaid
flowchart LR
    P0 --> P05[P0.5] --> P1 --> P2 --> P3 --> P35[P3.5]
    P35 --> P4 --> P5 --> P6 --> P7 --> P8 --> P9 --> P10 --> P11 --> P12 --> P13 --> P14
    P14 --> P15 --> P16 --> P17
    P16 --> P18
    P17 --> P19
    P18 --> P19 --> P20 --> P21 --> P22 --> P23 --> P24
```

P4–P6 and P16's static parts can overlap once P3.5 is in; the table above is the dependency
order, not a staffing plan.

### 31.4 Model-call classes and the provider-terms gate

| Class | What it is | Allowed from | Gate | Account before P10 | Controls |
|---|---|---|---|---|---|
| **Fake / scripted** | fake harness subprocess, scripted brain, stub verifier/review | P1 | none — unrestricted for architecture and acceptance testing | n/a | never spawns a real CLI (the test guard in `conftest.py` still blocks real `claude`) |
| **Tool-less structured call** | one headless `claude -p` (or provider) call with a JSON schema: brain, planner, inspection model pass, decision extraction, review judge | the phase that needs it (P4 optional, P6, P7) | **ADR-0021 must be passed first** | legacy `rotate.elect()` + `quota.reason()`; recorded as a pre-router RouteDecision | only through the P0.5 `llmcall` runner: write tools disallowed (`Write,Edit,NotebookEdit,Bash`), `--max-turns`, budget args, `HEADLESS_MARK`, quota latch on failure |
| **Tool-using agent execution** | a harness running a task with tools in a workdir | **P11, after P9** | ADR-0021 **and** the real policy engine (the adapter registry refuses real adapters while policy is the stub) | router (P10) | capability removal, policy hook/sandbox, approvals |

Rules:
- P0.5–P3.5 make no real model call and proceed without the provider-terms gate.
- Nothing assumes subscription-account automation is permitted. If ADR-0021 concludes the
  intended subscription workflow is not allowed, the architecture stays as it is and the
  accounts used for both real classes are API-key/provider accounts; subscription accounts
  remain available for the user's own interactive and manual sessions.
- The adapter-registry check ("refuses real adapters while policy is the stub") is a
  **lifecycle safety gate, not a security or trust boundary**. It fails closed: only the
  `FakeHarness` class itself is admitted, a policy counts as real only when it declares
  `is_stub = False` exactly, and the check runs at registration and on every lookup. But
  `is_stub` is a declaration by code in this repository, so the gate stops a phase from wiring
  up a real adapter early by mistake; it cannot stop code that lies. Whether an action is
  allowed is decided by the P9 Policy engine, with capability removal
  ([execution-architecture.md §2](execution-architecture.md)) as the primary enforcement.

## 32. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Provider terms do not allow headless automated use / multi-subscription rotation | unknown | high | gate before the first real headless model call (ADR-0021, §31.4); nothing assumes permission; API-key/provider accounts supported unchanged; router is provider-neutral |
| Harness CLI flags or stream formats change | high | medium | adapter contract tests on recorded streams; version pinning; `MISCONFIGURED` state |
| Hook bypass inside agent shells | medium | high | capability removal is primary; Core-only push/deploy; unclassified exec = strictest |
| stdlib HTTP server limits (HTTP/1.1, threads) | medium | medium | separate SSE pool, leader-tab stream, single user by design; revisit only if measured |
| Brain cost and latency | medium | medium | deterministic grammar for control, brain reserve, small/mid tiers for classification, prompt-cache-friendly prefixes |
| Scope size (25 phases) | high | high | minimal slice first; each phase gated; walking skeleton early |
| Two apps during the strangler period confuse users | medium | medium | V1 opened from the legacy app as a preview; one owner per artifact |
| Remote access misconfiguration exposes Core | low | high | HTTPS tunnel only, tokens required even on loopback, host allowlist, pairing only from a local session |
| Knowledge rot / stale context | medium | medium | validity windows, supersession, drift, staleness labels, forget |
| Windows specifics (no SIGSTOP, PID reuse, console windows) | high | medium | cooperative pause, create_time checks, `CREATE_NO_WINDOW` for headless runs |

## 33. Open questions

| # | Question | Status | Owner | Needed by |
|---|---|---|---|---|
| Q1 | Provider terms for automated headless use of subscription accounts and rotation across several subscriptions | OPEN (ADR-0021) | user | before the first real headless model call (P4 optional model pass, P6 extraction or P7 brain, whichever comes first) |
| Q2 | Remote access via Tailscale Serve as the documented default | PROPOSED (ADR-0010) | user | P15 |
| Q3 | ntfy as the default push channel (vs a native wrapper later) | PROPOSED | user | P15 |
| Q4 | SPA libraries (TanStack Query, React Router) | PROPOSED | engineering | P16 (the P3.5b SPA uses neither: p3.5b-design-gate.md D1) |
| Q5 | Exact hex values of the design tokens | PROPOSED | design review | P16 |
| Q6 | Voice channel in V1? | OPEN (research D1) | user | P16 |
| Q7 | Legacy worlds as a "Classic" appearance? | OPEN (research D3) | user | P16 |
| Q8 | UI languages at launch | OPEN (research D4) | user | P16 |
| Q9 | Import-all vs choose-projects onboarding | OPEN (research D5) | user | P22 |
| Q10 | Remote execution nodes timing | DEFERRED | user | after V1 |
| Q11 | Web Push via optional extra | DEFERRED | engineering | after V1 |
| Q12 | Vector search / FTS5 | DEFERRED | engineering | when retrieval quality is measured insufficient |
| Q13 | Archeus as an MCP server for other harnesses | DEFERRED | engineering | after V1 |
| Q14 | Multi-user workspaces | DEFERRED | user | after V1 |

## 34. Definition of done

**Architecture phase (this deliverable) is done when** (implementation plan's list): domain
objects, relationships, state machines, event contracts, mission/plan/task/execution contracts,
context contract, policy contract, routing contract, harness adapter contract, persistence
boundaries, presence/realtime contract, UI IA derived from the above, external research
recorded, decisions documented with reasons — each is linked from the table at the top.

**V1 release gate:**
- [ ] Mission state durable and independent of any session (G1)
- [ ] Mission lifecycle reliable across restarts, pauses, hand-offs (S2, G1)
- [ ] Context selection works, explainable and provenance-aware (G2)
- [ ] Policies enforced deterministically; approvals single-use and bound to actions (S5, G6)
- [ ] Routing deterministic and explainable; priority and allocation respected (S3, S4, S12)
- [ ] Harness adapters normalised and replaceable; Claude Code + Codex real (G7)
- [ ] Execution resumes after hand-off (S2)
- [ ] Verification and review prevent false completion (S6)
- [ ] Event-driven automation with loop guard (S10)
- [ ] Remote control works from a paired phone (S11)
- [ ] GUI, TUI, web and mobile expose the same world model (G3)
- [ ] Audit trail exists (G4)
- [ ] Emergency stop works with and without Core (G5)
- [ ] Repository re-inspection and drift work (S7)
- [ ] Legacy data migration tested (G8)
- [ ] Every traceability row green; no Critical design-review findings; no High security findings

---

## Appendix A — Adversarial review record

Following the migration kit's substitute for a bakeoff in redesigns, the draft plan was
red-teamed before these documents were written. 25 findings; outcomes:

| # | Finding (severity) | Outcome |
|---|---|---|
| 1 | Hook-based policy enforcement doesn't hold: pi has no hooks, Codex hooks gated, `guard_hook` fails open, regex classification bypassable (critical) | Fixed: capability removal first; Core-only push/deploy; fail-closed hook for Archeus executions; `enforcement` capability in routing; unclassified exec = strictest (ADR-0007) |
| 2 | ASK during a running headless execution undefined (critical) | Fixed: hook deny + halt → AWAITING_APPROVAL → resume with one-shot allow (execution §5) |
| 3 | Pause/stop not implementable on Windows as written (critical) | Fixed: cooperative pause, stop by pid+create_time, INTENT before spawn, boot reconciliation (state-machines §4) |
| 4 | Brain-as-MCP phase dependency, cost, self-approval (critical) | Fixed: structured-output brain; MCP deferred; brain cannot approve; deterministic control verbs (ADR-0006) |
| 5 | Allocation undefined for utilisation % (critical) | Fixed: ceiling semantics, halt on crossing, stale penalty, budgets when unknown (router §4) |
| 6 | SSE + single writer under stdlib server underspecified (critical) | Fixed: separate pools, heartbeats, ids-only events, leader tab, reader discipline (API §4) |
| 7 | No e-stop when Core is down (critical) | Fixed: STOP sentinel + `archeus estop` (execution §10) |
| 8 | Remote PWA needs HTTPS; guards loopback-hardcoded (critical) | Fixed: Tailscale Serve, paired-host allowlist, tokens always (API §5) |
| 9 | Subscription-terms feasibility unverified (high) | Recorded as OPEN gate (ADR-0021, Q1) |
| 10 | Context-pressure signal source missing (high) | Fixed: usage/window + PreCompact + compact_boundary; Core-derived checkpoints |
| 11 | Approval replay, non-idempotent commands (high) | Fixed: action-hash binding, single use, idempotency keys, step-up |
| 12 | No principal/actor model (high) | Fixed: Principal entity and scopes (domain §3.3) |
| 13 | Missing state machines (high) | Fixed: 14 machines in state-machines.md |
| 14 | Legacy/V1 data ownership undefined (high) | Fixed: ownership table (ADR-0019, migration §5) |
| 15 | Core lifecycle unspecified (high) | Fixed: target-architecture §4 |
| 16 | Phase dependency errors (high) | Fixed: P3.5, P9 gates adapters, narrowed P0.5, adapter contract frozen in P1 |
| 17 | Minimal slice not stated; meeting-note ingest missing (high) | Fixed: §31.2; context-and-knowledge §8 |
| 18 | Acceptance sources conflated (high) | Fixed: one traceability table (testing §2) |
| 19 | Verification with no verifier undefined (high) | Fixed: GenericVerifier = human acceptance; replan budget; independent flag |
| 20 | IA gaps: manual sessions, activity timeline, conversation model, settings placement (medium) | Fixed: Work manual sessions, Now activity, ADR-0015, Control sub-sections |
| 21 | Agent output as injection vector (medium) | Fixed: strict CSP, sanitised rendering, canonical approval cards |
| 22 | Secrets handling (medium) | Fixed: node-bound accounts, DPAPI, typed hashed tokens, pairing limits |
| 23 | Event retention and schema migrations (medium) | Fixed: API §3.4, target-architecture §5 |
| 24 | Router determinism and affinity (medium) | Fixed: input snapshot + affinity step (router §5) |
| 25 | Weak deliverable verification; gitignored sources; SPA build pipeline (medium) | Fixed: doc-lint gates; sources summarised and cited (kept gitignored by user decision); build pipeline in ui-architecture §2 |

The design review is Appendix B; the 30 self-review questions are Appendix C.

## Appendix B — Design review (Apple Design Skill, five lenses)

Run with the Apple Design Skill (`dickwu/apple-design-skill`) over the design system, the
wireframes (research Appendix A) and the UI architecture. Platforms: Windows desktop (SPA in the
Qt shell), web, PWA on iOS/Android, terminal. Contrast was **computed from the token hex values**
(WCAG relative luminance), colour distance as CIE76 ΔE; wireframes are low-fidelity, so spacing
and hit regions are specified rather than measured. HIG files opened: `accessibility.md`,
`layout.md`, `typography.md`, `color.md`, `dark-mode.md`, `tab-bars.md`, `sidebars.md`,
`sheets.md`, `feedback.md`, `loading.md`, `generative-ai.md`, plus `cross-platform.md`.

**Summary.** Rating after fixes: **Good**. Thesis: *a colleague whose work you glance at, verify
and direct*; remembered by the thread and by state being the only colour on screen. Before the
fixes the rating was *Needs work* (two High findings on colour meaning and sidebar placement).

| # | Severity | What | Why | Fix (applied) |
|---|---|---|---|---|
| B.1 | High | Hue accent `#7CC4FF` was ΔE 18 from `state.active` `#5AA9FF` on dark (1.31:1 between them) — below the design system's own ΔE ≥ 20 rule — and in Light the accent **was** the active colour (`#0B63CE` both). Blocked `#F07178` vs Failed `#FF8A65` ΔE 22 (dark) and 11 (light) | `color.md`: colours must stay distinguishable and mean one thing consistently | Removed the hue accent: primary = neutral inverted fill, links = underlined text, thread = near-white ink (`#F4F1EA`) / black ink on light; Failed shares the Blocked red with a different glyph and label; thread tints must be ΔE ≥ 30 from every state |
| B.2 | High | *Pause all* and *Devices* sat at the bottom of the sidebar (wireframe A.1) | `sidebars.md`: "Avoid putting critical information or actions at the bottom of a sidebar. People often relocate a window in a way that hides its bottom edge." | *Pause all* moved to the Now header, the tray and the command bar; Devices lives in Control |
| B.3 | Medium | App-level Dark/Light/High Contrast theme choice | `dark-mode.md`: "Avoid offering an app-specific appearance setting." | Appearance follows `prefers-color-scheme`, `prefers-contrast`, `forced-colors`, `prefers-reduced-transparency`; user choices reduced to thread tint, density, motion |
| B.4 | Medium | Swiping an approval sheet away had no defined meaning | `sheets.md`: "Support swiping to dismiss a sheet" and "Provide an alternative to the Done button" | Swipe = decide later (item stays in Attention); Approve/Reject are explicit |
| B.5 | Medium (judgment) | The active glyph "breathed" continuously while output flowed — an ambient loop on the most-watched element | Design rule 7 (research §15); `generative-ai.md`: specific progress text carries the meaning | One 240 ms pulse per batch of real output, at most every 2 s |
| B.6 | Medium (judgment) | TUI glyphs (◌ ‖ ◆) may be missing from Windows console fonts | information must not depend on glyphs the device cannot render | ASCII fallback set chosen by a startup probe |
| B.7 | Low | No menu bar in the Qt shell | `cross-platform.md`: desktop commands reachable from menus | Every command reachable from the command bar, row context menus and the tray; platform note, no change |

Measured after fixes: text 14.6:1 (dark) / 18.3:1 (light); `text-2` 8.3:1 / 7.7:1; state glyph
colours 6.2–9.6:1 on dark `surface-1`, 5.0–6.5:1 on white; focus ring 12.2:1 on dark — all above
4.5:1, so state colours may also carry state *labels*.

**What works (keep).** Glyph + label + colour for every state; the Why tab; approvals rendering
canonical actions; one-level sidebar with a two-level Control; container-query layout; specific
progress language; a four-tab mobile bar where every tab navigates (`tab-bars.md`: "Use a tab bar
to support navigation, not to provide actions").

**Removal test.** Removed the hue accent (B.1) and the breathing loop (B.5). The thread survives:
without it the link between what Archeus said and what it did disappears.

## Appendix C — Self-review (the prompt's 30 questions)

| # | Question | Answer | Where |
|---|---|---|---|
| 1 | Persistent AI colleague? | Missions owned by Archeus, presence from continuity, conversation acting on the world | §2, research §1 |
| 2 | Redesigned the old dashboard by accident? | No: home is Now (presence + attention + conversation); metrics moved to Control → Resources | research §17 |
| 3 | Conversation integrated with the operating model? | Messages create intents; cards are live domain objects; control verbs act directly | ADR-0015, §11 |
| 4 | Missions first-class? | Own entity, machine, inspector, API | domain §7.1 |
| 5 | Current state trustworthy? | Single writer, same-transaction events, Core-decided liveness, computed progress | target-architecture §7 |
| 6 | History distinct from knowledge? | Separate stores; promotion required | context-and-knowledge §1 |
| 7 | Context dynamically assembled? | Levels, retrieval, scoring, packages with reasons | context-and-knowledge §2 |
| 8 | Knowledge allowed to evolve? | Lifecycle, supersession, decay, forget, corroboration | context-and-knowledge §3 |
| 9 | Autonomy policy-controlled? | Policy engine, profiles, capability removal, approvals | §13, ADR-0007 |
| 10 | Harness, Account, Model, Session distinct? | Separate entities; session bound to account | router §1, domain §8 |
| 11 | Resource routing first-class? | Router module; decisions persisted and explained | resource-router.md |
| 12 | Missions survive session rotation? | Checkpoint hand-off; mission state unchanged | execution §6 |
| 13 | Verify rather than trust agent output? | Verification + review gate COMPLETED; progress not agent-reported | state-machines §2, §6 |
| 14 | Can Archeus replan? | REPLANNING with a budget; approvals superseded | §12 |
| 15 | Continuous repository understanding? | Re-inspection on change, schedule and merge | context-and-knowledge §6 |
| 16 | Architecture drift detected? | Checkable constraints, DRIFTED state, three-way resolution | state-machines §10 |
| 17 | Automations event-driven and policy-controlled? | Yes, with loop guard and simulation | §17 |
| 18 | Works across multiple devices? | Device pairing, SSE, per-user digest cursor | api-and-realtime §5 |
| 19 | Mobile as control surface? | PWA with Attention, pause/resume/stop, approvals with step-up | research §28 |
| 20 | GUI and TUI share the conceptual model? | One API, one nav table, one presentation table | ui-architecture §3 |
| 21 | Spatial visualisation meaningful? | Every visual variable mapped to a fact; list equivalent | research §26 |
| 22 | Design system uniquely Archeus? | State-only colour + thread + Why; passes the template check after B.1 | design system §1–2 |
| 23 | Accessibility built in? | Floors gated; OS appearance; reduced motion/transparency; keyboard; screen readers | design system §12 |
| 24 | Anthropic redesign research influenced the process? | Judge-first, red-team instead of bakeoff, walking skeleton, subsystem phases, three-strikes, feasibility gate | research §9, §31 |
| 25 | Apple Design Skill influenced quality? | Floors, template check, Appendix B fixes | Appendix B |
| 26 | External projects inspected? | Four repos at pinned SHAs + migration kit + skill | external-references.md |
| 27 | Verified vs interpretation distinguished? | [V]/[D]/[S]/[I] labels | research, references |
| 28 | Avoided copying blindly? | Adopted and rejected lists per reference; AGPL code not reused | research §11–14 |
| 29 | Implementable without guessing major decisions? | 21 ADRs; open items listed with owners; remaining PROPOSED items are library/hex choices and remote access | §33 |
| 30 | Acceptance scenarios supported? | Traceability table maps every scenario to phases and tests | testing-strategy §2 |

Known limitations: exact harness CLI flags are verified in P11 contract tests (execution §3);
provider terms (Q1) are unresolved; the source documents are gitignored, so readers on other
clones rely on the summaries here.

## Appendix D — Implementation-readiness corrections (2026-09-23)

A readiness review before P0.5 checked this plan against the code (import probes of every
reused module; reads of `memory`, `gui_api`, `quota`, `proc`, `connections`, the hook scripts,
`cli.py`, `pyproject.toml` and the home directory). Findings and the corrections applied:

| # | Sev. | Finding | Correction (where) |
|---|---|---|---|
| B1 | BLOCKER | P0 gated all work on the open provider-terms question | gate moved to before the first real headless model call; call classes defined (§31.1 P0, §31.4, ADR-0021) — approved by the user |
| H1 | HIGH | P3.5 acceptance "S1 passes" needed P7–P13 subsystems | P3.5 acceptance is `test_skeleton_vertical_slice.py`; S1 stays xfail until P13 (§31.1, testing-strategy §2) |
| H2 | HIGH | judge written in P1 against an API that exists only in P3.5 | `CoreClient` contract + phase-tagged xfail in P1; in-process then HTTP binding (testing-strategy §1.1) |
| H3 | HIGH | "P9 before real harness" was convention; real model calls earlier had no rules | call classes (§31.4); registry refuses real adapters while policy is the stub (P1 ports) |
| H4 | HIGH | legacy account hooks fire inside V1 executions; `limit_hook` could open a duplicate successor session | hook environment guard in P0.5 (migration-plan §3, ADR-0019) |
| H5 | HIGH | `~/.archeus/` is already a legacy per-project workdir (home-directory project) and deletable by legacy code | `ARCHEUS_HOME` resolved per platform (target-architecture §5.1); rollback text fixed (migration-plan §7) |
| H6 | HIGH | a browser SPA could not obtain the local token | local launch-code bootstrap in the URL fragment (api-and-realtime §5.1) |
| H7 | HIGH | crash between spawn and registry write could orphan and duplicate an agent; no stream to re-adopt; `spawn_detached` forces empty stdin | spawning marker, JSONL stream file, stdin file (execution-architecture §3.1, §4); `stdin_path` in the P0.5 proc seam |
| H8 | HIGH | P0.5 seams targeted modules already UI-free at import; missed `gui_api` import side effect, `build_launch_command` in `main`, CLI dispatch | P0.5 rewritten; `connections` split and `quota.assess` dropped; usage seam → P10, launch builder → P11, CLI → P3.5 |
| M1 | MEDIUM | router ceiling formulas disagreed | one formula per subject kind (resource-router §4, state-machines §9) |
| M2 | MEDIUM | `worst_window` reports unknown usage as 0 | public usage snapshot helper in P10 preparation |
| M3 | MEDIUM | checkpoint "decisions" had no source | `DECISION:` lines parsed from the stream (execution-architecture §6) |
| M4 | MEDIUM | e-stop semantics incomplete | sentinel persistence, re-arm, hook home discovery, Codex path (execution-architecture §10) |
| M5 | MEDIUM | packaging and SPA toolchain unplanned | P1 packaging; Node build/CI (ui-architecture §2) |
| M6 | MEDIUM | V1 legitimately writes two legacy files the ownership table said it never writes | shared ownership of `connections-cache.json` and `archeus-limits.json` (migration-plan §5, ADR-0019) |
| L1 | LOW | judge floor 23 vs table rows | floor = number of traceability rows, derived (testing-strategy §4) |
| L2 | LOW | SQLite features vary by build | min 3.31, no `RETURNING`/`STRICT` (P2) |
| L3 | LOW | context window unknown when catalogue unreachable | fallback table (execution-architecture §6) |
| L4 | LOW | claim that V1 "ends" the shared-import-package hazard | reworded (target-architecture §3, ADR-0001) |
| L5 | LOW | "replies stream in" vs ids-only events | replies arrive as whole messages in V1 (ui-architecture §4.1) |
| L6 | LOW | rotation threshold mapped to allocation 98 vs default 80 | import sets allocation 80 and records the old threshold for review (migration-plan §4) |
| L7 | LOW | "every entity" vs "defer fields" in P1 | every entity with minimal fields (§31.1 P1) |
| C1 | LOW | P1 checkpoint: the correction patch inserted four passages three times (§11 brain paragraph, P3 guard sentence, P6 extraction sentence, §31.4) | duplicates removed; text unchanged |
| C2 | MEDIUM | P1 checkpoint: `exe_` named both the Execution id and the execution token | execution tokens are `hook_…` (the existing `ARCHEUS_HOOK_TOKEN`); token prefixes are a namespace disjoint from id prefixes (domain-model §1, api-and-realtime §5.3, `ids.TOKEN_PREFIXES`) |
| C3 | MEDIUM | P1 checkpoint: the legacy Qt shell's cache already lives in `%LOCALAPPDATA%\Archeus`; "delete `ARCHEUS_HOME`" would have deleted it | per-entry ownership table (target-architecture §5.1); reset removes V1 entries by name (migration-plan §7) |
| C4 | LOW | P1 checkpoint: the stub-policy adapter gate could be read as a security boundary | stated as a lifecycle safety gate; authority is the P9 engine plus capability removal (§31.4) |
| C5 | LOW | P1 checkpoint: the Integration machine had no host entity | it is `Task.integration_state`, not an entity (domain-model §7.3, state-machines §13) |
| C6 | MEDIUM | P2 checkpoint: the pre-migration backup reused the daily name and could replace that day's daily backup | its own name, `migration-archeus-vA-to-vB-YYYYMMDD-HHMMSS[-N].db`, created without ever overwriting (hard link from the finished temp copy); daily retention never matches it (target-architecture §5) |
| C7 | MEDIUM | P2 checkpoint: `transition()` was placed in P3 by this plan and in P2 by the P2 requirements | split by layer: P2 owns the transactional primitive (version check, table edge, state, version bump, event, reason, one transaction); P3 owns guards, action semantics, policy and lifecycle orchestration on top of it (§31.1 P2/P3) |
| C8 | MEDIUM | P2 checkpoint: the event actor could be read as a principal id (domain-model) or an execution id (the api-and-realtime example showed `exe_…`) | the actor is always the causing principal: `actor.id` is a `prn_…` id, validated by `Event` and by the writer for `created_by`; execution provenance goes in `subject`, `cause_chain` or the payload. Stored as `actor_kind` + `actor_id` (domain-model §9.5 `actor_principal_id`) |
| C9 | LOW | P2 checkpoint: `Plan.version` collided with the row's optimistic-concurrency `version` | the domain field is `plan_version`; `version` means the row's concurrency version everywhere. A test walks every entity for clashes with the row metadata; the one remaining clash (`KnowledgeItem.body` vs the `body` column) is refused by the codec and belongs to the phase that persists knowledge |
| C10 | LOW | P2 checkpoint: the cursor contract named only the stale case | malformed → `400`; behind retention or ahead of the highest assigned seq → `410 cursor_expired` (api-and-realtime §3.4) |
| C11 | LOW | P2 checkpoint: the in-process client registers its own principal | a P2 **bootstrap** only, so persistence can run; who may register a principal is decided by the auth/policy layer (P3.5 local bootstrap, P9 policy) |
| C12 | LOW | P2 checkpoint: the 500 commands/s floor was asserted on whatever machine ran CI | 500/s stays the architectural target, asserted on a developer machine; on CI (`CI` set) the test asserts a 200/s regression floor, best of three batches, because hosted runners' fsync cost is not ours to set |

No phase, technology or feature was added; P3.5 gained the minimal local node it always
implicitly needed to run the fake harness, taken from P11's scope.
