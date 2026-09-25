# Archeus V1 — Resource Router

Status: **DECIDED** (ADR-0005). Entities: Harness, Account, Model, ModelOffer, Session,
ResourcePolicy, UsageSnapshot, UsageLedger, RouteDecision in [domain-model.md §8](domain-model.md).

## 1. What the router is for

Given *something that needs to run* — a task, a brain call, a review, a verification that needs
a model — the router picks exactly one **(harness, account, model)** triple, or explains why none
is eligible, and records the decision so anyone can later ask *"why did Archeus use Account B?"*
and get an answer generated from evidence.

It is not a load balancer. It is a deterministic, explainable function of:
capability · policy · availability · priority · allocation · limits · affinity ·
project/mission restrictions · model requirements · cost/latency preference.

**Harness, Account, Model and Session are four different things** (spec §14, prompt §12):

| Object | Example | Owned by | Changes when |
|---|---|---|---|
| Harness | `claude_code` 2.4.x | node discovery | CLI installed/upgraded |
| Account | "Personal Max" = `~/.claude`; "Work" = `~/.claude-work`; "OpenAI key #1" | user registration | login, logout, key rotation |
| Model | `claude-opus-5-5`, `claude-sonnet-5`, `gpt-5.x-codex` | catalogue (`models.roster`) | provider release |
| Session | a Claude session UUID under one account | execution | every execution/hand-off |

A Session is bound to (harness, account). Moving work to another account is therefore always a
**checkpoint hand-off into a new Session**, never "switch account mid-session".

## 2. Registration

| Step | Source | Result |
|---|---|---|
| Harness discovery | node probes executables (today's `harnesses.HARNESSES` descriptors + `exe_setting`) | Harness rows with `capabilities`, `enforcement`, `installed_version` |
| Account registration | user in Control → Resources (import from legacy `settings['accounts']` / `settings['homes']` at migration) | Account rows (`node_id` = local), `auth_kind`, `home_ref` |
| Auth probe | adapter `authenticate()` (cheap, no inference) | health UNVERIFIED → AVAILABLE / UNAUTHENTICATED |
| Model offers | adapter `capabilities()` + `models.roster()` newest-per-family logic | ModelOffer rows; stale offers marked unavailable after 24 h |
| Resource policy | user sets priority, allocation, reserve, budgets, project rules, fallback | ResourcePolicy row; changes are events |

Defaults at first run: every account `priority` in registration order, `allocation_pct` 80,
`reserve_pct` 10, `fallback: ask`, `brain_reserve_pct` 10, no budgets.

## 3. Capabilities and enforcement

A **requirement** is computed from the subject:

```yaml
requirements:
  capabilities: [code_edit, shell]      # from task.kind + task.capabilities_required
  action_classes: [write_repo, exec]    # from task.action_classes
  min_model_tier: mid                   # blast radius: see §6
  min_context_window: 200000
  structured_output: false
  interactive: false
  project_id: prj_…
  preferred: {accounts: [], harnesses: []}   # mission.resource_preferences
  forbidden: {accounts: [], harnesses: []}
  max_cost_band: medium
```

**Archeus's own calls** (ADR-0022) are subject `archeus_call` with a `purpose`
(knowledge_extraction, lesson, generation, brain, planner; the review judge is the same call
class but keeps its own `review` subject and ceiling). Their requirement is
`capabilities: [headless]` and, when a schema is asked, `structured_output: true`, which every
`headless` harness satisfies — natively or in the prompt — because Core validates the result;
it never eliminates a harness for lacking a schema flag. `preferred`/`forbidden` for this
subject come from the user's own-call choice (global or workspace scope; legacy
`headless_harness` / `headless_harness_model`), a preference unless the user marks it required,
in which case it is a constraint. A model is eligible only as an offer of the candidate account,
in that harness's vocabulary; an unknown tier or context window (a local model) counts as the
smallest, so a requirement's minimum excludes it rather than trusting it.

Every harness declares `enforcement`:

| Value | Meaning | V1 harnesses |
|---|---|---|
| `hook` | Archeus can intercept each tool call and deny/halt (PreToolUse-style) | claude_code |
| `sandbox` | Harness enforces filesystem/network boundaries itself; Archeus sets them at start | codex (`workspace-write`, network off unless `web` is allowed) |
| `none` | No interception possible | pi, generic_cli (tool-using execution DEFERRED; `archeus_call` is read-only by construction, so enforcement does not apply to it — ADR-0022) |

**Eligibility rule:** a harness with `enforcement: none` is eligible only if *every* action class
in the requirement evaluates to ALLOW (not ASK, not ALLOW_WITHIN_BOUNDARY) under the task's
policy scope. A `sandbox` harness is eligible for ALLOW_WITHIN_BOUNDARY only when the boundary
is expressible in its sandbox (paths yes; per-command globs no).

## 4. Priority and allocation

**Priority** = order of preference among eligible accounts. Nothing more.

**Allocation** = how much of an account Archeus may consume. Providers expose *utilisation of a
window* (Anthropic OAuth usage: 5-hour and 7-day percentages; Codex: rate limits from rollout
files), and that percentage includes the user's own manual use. Archeus cannot attribute the
provider's number to itself, and the number lags. So allocation is defined as a **ceiling on the
observed window**, not a share of a pie:

```text
effective_ceiling(account)    = allocation_pct − reserve_pct
ceiling(account, kind)        = effective_ceiling(account)                       if kind = archeus_call (brain and every other own call)
                              = effective_ceiling(account) − brain_reserve_pct   if kind ∈ {task, review}
worst(account)                = max over windows of utilisation_pct, from the latest UsageSnapshot
                                (unknown ≠ 0: see allocation_known below)
can_start(account, kind, s)   = worst(account) + projected(s) < ceiling(account, kind)
must_halt(execution)          = worst(account) ≥ allocation_pct        (checked on each usage refresh)
```

- `projected(task)` is a small conservative bump by task size band (S 1%, M 3%, L 8% of the 5 h
  window; tuned from the ledger over time), so a long task does not start at 79.9% and blow
  through an 80% ceiling.
- A running execution that crosses `allocation_pct` is **halted at its next tool boundary** and
  hands off via checkpoint (to another account if policy allows fallback, else the task goes
  BLOCKED with "allocation reached, resets at …").
- Usage freshness: before routing, if the account's newest snapshot is older than 120 s (5 h
  window) the router asks for a refresh (`usage.fetch_usage` / rate-limit read) with a 3 s
  timeout; on timeout it uses the stale value **plus** a staleness penalty of 5 points and
  records `usage_age_s` in the decision.
- **Accounts with no readable window** (API keys without a usage endpoint, proxies):
  `allocation_known = false`. They are governed by **ledger budgets** (`tokens_per_day`,
  `cost_per_day`, `concurrency`). An account with `allocation_known = false` and no budgets is
  eligible **only as a fallback**, and only when its `fallback` is `allow`.
- `brain_reserve_pct` is what the two `ceiling` cases express: the brain may use up to
  `effective_ceiling`, tasks and reviews up to `effective_ceiling − brain_reserve_pct`.
  Archeus can therefore always still *think* (and explain it is out of capacity) when task
  capacity is gone. `projected(s)` is 0 for a brain call.
- The legacy `quota.worst_window` is **not** used: it returns 0 when usage is unknown ("not
  known is a pass"), which would read as an empty account. The P10 preparation seam exposes
  `(windows, observed_at, status)` instead.

Example: Account A P1 100%, B P2 80%, C P3 50% (the spec's example), reserve 10 each:

| Account | allocation | reserve | tasks may start while worst < | brain may run while worst < |
|---|---|---|---|---|
| A | 100 | 10 | 80 (100−10−10 brain) | 90 |
| B | 80 | 10 | 60 | 70 |
| C | 50 | 10 | 30 | 40 |

## 5. The algorithm

Deterministic. Same inputs (persisted in `input_snapshot`) → same decision.

```python
def route(subject, now) -> RouteDecision:
    req  = requirements_for(subject)                              # §3
    snap = snapshot(now)       # health, usage (refreshed if stale), ledger totals, policy version
    cands = all_offers()       # (harness, account, model) triples
    steps = [
      ("capability",   lambda c: c.harness.has(req.capabilities) and c.model.tier >= req.min_model_tier
                                  and c.model.context_window >= req.min_context_window),
      ("enforcement",  lambda c: enforcement_ok(c.harness, req, policy_for(subject))),     # §3
      ("policy",       lambda c: policy.allows_resource(subject, c) != DENY),             # e.g. project_deny, harness forbidden
      ("restriction",  lambda c: project_allowed(c.account, req.project_id) and not forbidden(c, req)),
      ("health",       lambda c: c.account.health in (AVAILABLE, CONSTRAINED)),
      ("allocation",   lambda c: can_start(c.account, subject, snap) and budgets_ok(c.account, snap)),
    ]
    rejected = []
    for name, ok in steps:
        keep = [c for c in cands if ok(c)]
        rejected += [(c, name, reason(name, c, snap)) for c in cands if c not in keep]
        cands = keep
    if not cands:
        return fallback_or_block(subject, rejected, snap)          # §7
    cands = order(cands, key=lambda c: (
        0 if affinity(subject, c) else 1,          # 1. stay where the mission already runs (cache + resume)
        0 if c.account in req.preferred.accounts else 1,
        c.account.policy.priority,                 # 2. user priority
        tier_fit(c.model, req),                    # 3. smallest model tier that satisfies the requirement
        c.account.health == CONSTRAINED,           # 4. prefer AVAILABLE over CONSTRAINED
        cost_rank(c, req),                         # 5. cheaper, then
        latency_rank(c),                           # 6. faster
        c.account.id))                             # 7. stable tie-break
    chosen = cands[0]
    return record(subject, chosen, rejected, snap, cands[1:])      # RouteDecision + event
```

**Affinity (step 1 of ordering)** keeps a mission on the account/harness its previous execution
used, as long as that account is still eligible. Without it a P1 account recovering from a limit
would steal a mission mid-flight, which throws away the prompt cache and forces a hand-off for
no benefit. Affinity is ignored when the user reprioritises accounts explicitly ("use account A
first") — that command clears affinity for the mission.

**Tier fit** implements "model tier by blast radius" (migration kit): plan authoring, review,
architecture decisions → `large`; implementation of a well-specified task → `mid`; mechanical
edits, classification, summaries → `small`. The task's `min_model_tier` is set by the planner;
the router never goes *above* what is needed unless nothing smaller is eligible (and records it).

## 6. Effort and cost economics

- Effort is a per-execution parameter (today's `config.MODEL_EFFORT_FRONTIER` / Power slider).
  The planner sets it by task kind; the router may lower it when the account is CONSTRAINED.
  Rationale from the Claude Platform cost guidance: *a stronger model at low effort can be cheaper
  than a weaker model working hard* — so tier and effort are chosen together, not maximised.
- **Prompt-cache preservation:** brain calls and task prompts are assembled with a stable prefix
  (identity, standards, project summary) and a variable suffix (task, context package), so
  repeated calls on the same account hit the provider cache. Affinity exists partly for this.
- **Prompt hygiene on model upgrade:** when a new model family member becomes current
  (`models.roster`), an automation proposes a review of Archeus's own prompt templates (remove
  emphasis boosters / verification rituals that newer models do not need). Proposal only.

## 7. Fallback, failure and retry

| Situation | Behaviour |
|---|---|
| No candidate survives | `fallback_or_block`: if any *rejected* candidate was rejected only by `allocation`/`health` and its account's `fallback` is `allow` → pick it (recorded as fallback). If `ask` → task AWAITING_APPROVAL with an Approval "Use Account C (P3) because A is limited until 14:30 and B is at its 80% ceiling?". If `deny`/none → task BLOCKED with the earliest `limited_until` as the unblock time. **Never silently violate policy to keep work moving** (spec §16). |
| Execution fails with a limit error (`quota.is_limit_error`) | account → LIMITED (`limited_until` from the error or snapshot); execution hands off via checkpoint; task re-routes (affinity dropped because the failure is resource-attributable). |
| Error storm (5 non-limit errors in 10 min) | breaker DEGRADED → OPEN (state-machines §9); tasks re-route. |
| Auth failure | UNAUTHENTICATED; Attention item "log in to Work account"; tasks re-route. |
| Retry | Task retry re-enters routing; same inputs → same answer unless state changed; the decision records `retry_of`. |

## 8. Explainability

`RouteDecision.explanation` is **generated from the structured record**, never written by a
model. Template (localisable):

> I used **Account A** (Claude Code, `claude-sonnet-5`) because it is your priority-1 account,
> it had 42% of its 5-hour window used against a 80% ceiling for tasks, and this mission was
> already running there.
> Not used: **Account B** — 7-day window at 83%, above its 80% allocation. **Account C** —
> excluded for project *Payments* by your resource rules. **pi** — cannot enforce the
> `write_repo` boundary this task needs.

The brain may paraphrase an explanation in conversation, but the card it attaches is the
structured decision, and the *Why* tab renders the raw record (candidates × elimination step ×
reason, input snapshot with ages).

## 9. Auditability

- Every call produces a RouteDecision row + `route.decided` event (including brain calls).
- `input_snapshot` stores usage values *with their observed_at*, health, ledger totals, policy
  version and the ResourcePolicy versions used → a decision can be **replayed** in tests and in
  support ("would the router choose differently now?").
- Policy interaction: the router asks the policy engine only *resource* questions (may this
  account/harness be used for this project/mission?). *Action* questions (may this task push?)
  are asked by the Execution Manager and the hooks at action time.

## 10. Worked scenarios

**A. Normal.** A P1 100%, B P2 80%, C P3 50%. A at 35% of 5 h. Task M-size code change.
→ A selected (priority, 35 + 3 < 80). B, C not eliminated; ordered after A.

**B. A reaches its limit mid-mission.** A's 5 h window hits 100% during task 3. Execution fails
with the limit message → A LIMITED until 16:05 → checkpoint derived → task re-routes: A rejected
(health), B at 20% → B selected. Policy on B is `fallback: allow` → no question asked; Now shows
"Continuing on Account B — Account A is limited until 16:05." (Scenario 4.)

**C. Fallback needs approval.** Same, but B is at 78% (ceiling 60 for tasks) → rejected
(allocation). C has `fallback: ask` → task AWAITING_APPROVAL; phone notification "Continue
*Dashboard* on Account C (P3)?". Approve → routes to C; reject → task BLOCKED until 16:05.

**D. "Use account A first, then account B if necessary."** Parsed by the brain into a
mission-scoped `resource_preferences = {preferred: [A], fallback_chain: [B]}` and shown as a
card for confirmation; it overrides global priority *for this mission only*.

**E. "Why did you choose this model?"** Control-verb grammar recognises `route why` / "why …
model/account" → answers from the latest RouteDecision for the referenced mission/task with no
model call.

## 11. Tests (see testing-strategy.md)

Property tests over generated account sets: allocation is never exceeded at start; affinity never
selects an ineligible account; DENY never produces a selection; decisions are identical when
replayed from `input_snapshot`; fallback only happens when `fallback != deny`. Fake usage feed
drives Scenarios 3/4/12.
