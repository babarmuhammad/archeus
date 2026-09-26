# P9 design gate: policy, autonomy and authorization

Status: **IMPLEMENTED (P9).** Written 2026-09-26 against `e2f2184` (P8 accepted); the decision
pass approved D1–D26 with binding clarifications (§26); the as-built record and its deviations
are §29. Every item is marked with where it comes from:

- **[spec]** already specified by the V1 architecture (plan, domain model, state machines, ADRs);
- **[clar]** a clarification of an existing contract that the documents leave open, or that the
  code has already settled differently;
- **[new]** a genuinely new contract decision.

Every [new] item, and every [clar] item that changes a frozen P1–P8 behaviour, is in the decision
pass (§26) and needs approval. The conflicts with frozen contracts are listed on their own (§27).

Sources read, and precedence: the plan (**§13**, §11, §12, §27, §31.1 **P3, P3.5 as-built
checkpoints (1)–(6), P8 as-built, P9**, §31.4), **ADR-0004, ADR-0006, ADR-0007, ADR-0020,
ADR-0021 (still OPEN), ADR-0022, ADR-0023**, domain-model **§3.3, §7.1–§7.3, §9.1–§9.3, §10**,
state-machines **§0, §2, §2.1, §3, §4, §5**, execution-architecture **§1, §2, §5, §10**,
resource-router **§3, §5**, migration-plan, testing-strategy **§1.1, §2 (S5, S6, G6), §3, §4**,
the P3.5b, P4–P8 gates, and the code: `archeus/core/{ports,engine,runtime,calls}.py`,
`core/domain/{actions,entities,states,guards,events,values,ids}.py`,
`core/application/{commands,work,planning,lifecycle,queries,grammar,errors}.py`,
`core/planning/{planner,worker,validate}.py`, `harnesses/{registry,fake,fake_agent}.py`,
`api/{routes,auth,server}.py`, `infra/db/{writer,migrations/0001–0007}`,
`infra/eventlog/{outbox,retention}.py`, the judge (`client.py`, `support.py`, S5, S6, G6,
`test_traceability.py`, `fixtures/brain/recordings.json`). Where a document and the code disagree,
the code states what exists; the frozen judge is the most specific source.

---

## 1. What P9 is

P8 ends at a **PROPOSED** PlanVersion: validated, immutable, digested, ready for the policy stage,
and decided by the P3 plan gate over a *stub* Policy port. P9 replaces that stub with the real,
deterministic policy engine and adds the authorization records that bind every decision to the
exact plan version and the exact action.

```
PROPOSED plan version (P8)                          the P3 plan gate, same transaction (P8 D4)
  -> items: every (task, action class) of the version, canonicalised (§3.3)
  -> PolicyEngine.evaluate(item, ctx)   pure: rules GLOBAL..TASK, locks, strictest, boundary (§4-§6)
  -> ONE writer transaction:
       all ALLOW / ALLOW_WITHIN_BOUNDARY, cost under ceiling
           -> PolicyDecision(stage plan)  + plan PROPOSED -> APPROVED  + mission plan_auto_approved
       something to ask (ASK, or cost band)
           -> PolicyDecision(stage plan)  + Approval(plan, PENDING)   + mission plan_needs_approval
       any DENY
           -> nothing written by propose_plan (P3.5); the responding command records
              PolicyDecision(DENY) + Mission.planning_blocked {kind: policy}
              (REASONING -> BLOCKED: plan_denied; PLANNING / REPLANNING wait in place)  (§11)
user decides the Approval (POST /v1/approvals/{id}/decide, echoing its action_hash)
  -> eligibility re-judged in the deciding transaction (§10.5)
  -> approve: Approval APPROVED + plan APPROVED + mission approve (now guarded)
     reject:  Approval REJECTED + plan REJECTED + mission reject (-> CANCELLED)
     request_changes: Approval REJECTED + plan REJECTED + mission request_changes (-> PLANNING)
task dispatch (the P3.5 dispatch_task, the only existing consumer of an authorization)
  -> re-evaluates the task's items at stage dispatch; covered -> proceeds; DENY -> refused
     (unchanged); an ASK nothing covers -> mission block + Approval(task)   (§12)
```

P9 answers **may**; it never answers **with what** (P10) or **does it** (P11). The invariant that
carries every phase since P7: *the model proposes; Core validates and decides* — P9 adds *and
nothing is authorised except an exact, recorded identity under an exact, recorded policy.*

## 2. Boundaries

| In P9 | Not in P9 |
|---|---|
| the policy engine (pure), rules, profiles, the built-in floor | resource routing, harness / account / model / node choice (P10) |
| PolicyDecision records for plan, dispatch and action stages | spawning, dispatching a process, resume, stop, pause, e-stop commands (P11) |
| Approvals of plans, of tasks, and of single actions (the action-stage command) | the policy hook and `POST /v1/hook/evaluate`, hook tokens, canonicalising a tool call (P11) |
| the authoritative `action_hash` and plan-version binding | session continuity, checkpoints, hand-off (P12) |
| stale / superseded plan refusal; supersession of approvals | verification, review, integration (P13) |
| the decide contract, idempotency, trigger authorization | automation, triggers, schedules (P14) |
| read routes + decide + rule admin + simulate | pairing, step-up PINs, paired devices (P15); approval cards and chat `approve` (P16) |

P9 is the **first real authorization boundary**. The adapter registry gate (plan §31.4) was a
lifecycle safety gate; P9's engine is the thing it was waiting for (§14.3).

---

## 3. The policy question (req. 1)

**Question [spec] (plan §13):** *May Archeus perform this exact action, in this exact context,
right now?* It is asked of one canonical action in one context, never of a mission or plan
globally. A plan is authorised as the **set of its items** (§3.3), each asked separately and
recorded together.

### 3.1 The inputs [spec + clar]

| Input | What it is | Source (gathered by the application, never read by `evaluate`) |
|---|---|---|
| **action** | `Action{class, target, argv?, diff_hash?, environment?, paths?}` (§3.3) | the plan version's tasks (plan, dispatch stages); P11's canonicaliser (action stage) |
| **action identity** | the binding `{kind, mission_id, plan_id, plan_version, plan_digest, task_id?, task_key?, execution_id?}` | the rows of the transaction (§7) |
| **subject** | what is being authorised: `plan` / `task` / `action` | the calling command |
| **principal** | `{kind, id}` of the actor asking | the command's actor |
| **stage** | `plan` (plan gate), `dispatch` (task dispatch), `action` (per tool call, P11 caller) | the calling command |
| **world context** | `workspace_id`, `user_id`, `project_id` (and later the System's `environment`) | Mission row; project from P4 |
| **mission** | id, state, `autonomy_profile` | Mission row |
| **plan version** | id, version, `digest` (recomputed from rows and compared), in force or not | Plan + Task rows (P8) |
| **task** | id, key, declared `action_classes`, `capabilities_required`, `touches` | Task row (frozen contract, P8) |
| **requested capability** | task `capabilities_required`, mapped to the classes they imply (§3.3) | Task row |
| **resource implications** | *not an input.* P9 records what enforcement an item needs (§14.1); P10 matches resources to it | — |
| **policy** | every active rule applicable to the scope chain, the built-in floor, the expanded profiles, `policy_version` | `policy_rules` rows + code constants |
| **current state** | `now` (the transaction's clock), `estop_armed` (the STOP sentinel exists, execution-architecture §10) | the writer transaction; `run/STOP` |
| **constraints** | cost band vs the auto-approve ceiling (plan gate only; P3.5 fixture until P10) | Plan row (P8 D9) |
| **provenance** | the rules' sources, author principals, revisions; the plan's RouteDecision / ContextPackage | rows |

`evaluate(action, ctx)` is **pure** [spec: guards are pure, state-machines §0]: the application
gathers `ctx` inside the transaction that will commit the move (`authorization.context(tx, …)`),
so a decision is never judged against rows other than the ones being changed. The Policy port
signature (`evaluate(action, ctx) -> PolicyDecision`) is unchanged; the stubs ignore the extra
context. [clar]

### 3.2 Stages

| Stage | Asked by | When | P9 implements |
|---|---|---|---|
| `plan` | the P3 plan gate inside `Work.propose_plan` | a version is recorded | yes |
| `dispatch` | `Work.dispatch_task` (P3.5; the execution manager's in P11) | a task is about to get an Execution | yes |
| `action` | the policy hook via `POST /v1/hook/evaluate` (P11) | an execution attempts a tool call | the **command** (`Authorization.evaluate_action`), tested directly; the route and its caller are P11's (**D19**) |

### 3.3 Canonical plan-level items [new] (**D6**)

For each task of the version, the items are `declared ∪ implied`:

- `declared` = `task.action_classes` (P8 contract);
- `implied` = classes its `capabilities_required` make inevitable: `code_edit → write_repo`,
  `shell → exec`, `web → web` (`long_context`, `vision` imply nothing). Recorded with
  `implied_by`, so the approval presents what the task will really do and a planner cannot keep an
  `exec` out of the approval by declaring only `shell`.

Each item is `Action(class=c, target='task:<key>', paths=<task.touches or None>)` — the target
convention `Missions.snapshot` already uses. `Action` gains one **optional** field, `paths`
(a tuple of project-relative globs). [clar, additive to P1 §9 `Action`: `canonical()` omits
`None` fields, so every existing canonical form and test is unchanged.] Fields that only the
action stage can know (`argv`, `diff_hash`, a branch, a host, `unclassified`) are P11's
canonicaliser's; the engine's rule for them is fixed now (§5.2, §6).

---

## 4. Rules and the scope hierarchy (req. 2)

### 4.1 Levels [spec + clar] (**D1**)

`GLOBAL → USER → WORKSPACE → PROJECT → MISSION → TASK → ACTION` [spec, plan §13], unchanged:

| Level | `scope_ref` | Who writes it |
|---|---|---|
| GLOBAL | — | **code only**: the built-in floor and the baseline profile (§5), versioned with `PROFILES_VERSION` |
| USER | the user id (V1 is single-user) | the user's default autonomy profile + explicit user rules |
| WORKSPACE | a workspace id | explicit rules (the workspace profile is deferred: V1 has one workspace) |
| PROJECT | a project id | explicit rules |
| MISSION | a mission id | the mission's autonomy profile + explicit rules |
| TASK | a task id (one task of one plan version) | explicit rules + the implicit contract rule (§4.4) |
| ACTION | an `action_hash` | **approvals only** — never a rule |

[clar] P1's `entities.SCOPE_LEVELS` already stops at TASK and domain-model §9.1 lists no ACTION
level for PolicyRule; plan §13's `matching_rules` names ACTION. They agree once ACTION is read as
what it is in the pseudo-code: `one_shot_allow_matches(action)` — the most specific "rule" is a
valid approval of exactly this action identity, and it can only answer an ASK (§4.2 step 7). So
rules are GLOBAL…TASK, approvals are the ACTION level, and nothing else is.

A TASK rule names a task id, and task ids belong to one plan version, so a task rule never
carries into a replan — the same non-leak property approvals have (§8).

### 4.2 Evaluation (precedence, locks, conflicts) [spec + new detail] (**D2**)

```
evaluate(action, ctx):
 0. ctx.estop_armed                      -> DENY 'emergency stop armed'            (plan §13)
 1. applicable = active, unexpired rules on ctx's scope chain with rule.class == action.class
                 and match(rule, action)                                          (§6.1)
    + the implicit TASK contract rule (§4.4); 'unclassified' actions (§6.3)
 2. applicable empty                      -> DENY 'policy_missing'                (fail closed)
 3. depth(rule) = 2*level + (1 if explicit else 0)   # explicit beats a profile at the same level
    specific   = applicable rules at the greatest depth
 4. effective  = {strictest(specific)} ∪ {every LOCKED applicable rule at a smaller depth}
 5. decision   = strictest(effective)      order: DENY > ASK > ALLOW_WITHIN_BOUNDARY > ALLOW
 6. decision == AWB: inside every AWB boundary in effective?                       (§6.2)
      inside   -> AWB (checked / deferred predicates recorded)
      outside  -> strictest of those rules' `outside` (ASK | DENY, default ASK)
 7. decision == ASK and stage != plan: a valid approval covers this identity (§8)?
      -> ALLOW, citing the approval (action stage: consumes it)
 8. step_up = decision == ASK and class in (deploy, destructive)
 9. record everything that led here (§9)
```

- **Inheritance:** a level with no applicable rule for the class inherits the deepest broader one,
  because `specific` is the deepest level that has any. [spec]
- **Override:** a deeper unlocked rule overrides broader unlocked rules **in either direction**
  (tighten or loosen). [spec: "most specific non-shadowed rule per class"]
- **Locks:** a locked rule is always in `effective`, so a deeper rule can tighten it but never
  loosen it. **DENY is always locked** (P1 `PolicyRule._check` already enforces it). A locked
  ALLOW is legal and meaningless (nothing is looser). [spec]
- **Explicit deny:** a DENY anywhere on the chain that matches is in `effective` and wins. No
  approval, profile, level or autonomy overrides it; a DENY is never a question for a human
  (P3.5, unchanged). [spec]
- **Conflict (same depth, different decisions):** strictest wins, and the record carries
  `conflicts: [rule ids]` so the explanation says two rules disagreed. [new, deterministic]
- **Missing policy:** unreachable by construction (the GLOBAL baseline has a rule for every class,
  a unit test asserts it), and DENY if it ever happens — a configuration fault is not something a
  human can meaningfully approve. [new]
- **Determinism:** `evaluate` reads nothing but its arguments; rule order does not matter (the
  sort key is `(depth, strictness, rule id)`); a recorded decision replays to the same result
  from its own snapshot (§9, property test U-P3).

### 4.3 Rule shape [spec + new fields] (**D17**)

`PolicyRule` (domain-model §9.1; P1 has `scope_level, scope_ref, action_class, decision, locked`)
gains: `match` (§6.1), `boundary` + `outside` (§6.2), `expires_at?` (a temporary rule is ignored
after it — "allow pushes for the next two hours"), `source` (`builtin` | `profile:<name>@<v>` |
`user`), `author_principal_id`, `note`, `revision`, `supersedes_rule_id?`, `retired_at?`.
**Rules are immutable** [new]: a change is *retire + insert the next revision* in one command, and
both are events with before/after (domain-model §10). Decisions snapshot the rule **contents** they
used, so a retired rule never changes what an old decision says.

### 4.4 The implicit TASK contract rule [new] (**D6**)

At the dispatch and action stages, a class **outside** the task's `declared ∪ implied` items is
evaluated with a virtual **locked ASK** at TASK level: an agent cannot silently exceed its
dispatch contract, and a human can still approve the deviation. At the plan stage the items *are*
the contract, so it never applies there.

---

## 5. Autonomy and profiles (req. 3)

### 5.1 What autonomy is [spec + clar] (**D5**)

P9 owns authorization, not reasoning. **Autonomy is a named rule bundle (a profile) expanded at
the level it is assigned to** — plan §13's *Careful / Standard / Autonomous*. It is never a flag
the engine consults, never a blanket permission, and never an input to the brain or the planner.

| Assigned at | Field | Default |
|---|---|---|
| GLOBAL | built in | `careful` (the baseline — every class has a rule) |
| USER | `User.autonomy_profile` [new field] | `standard` (plan §13: "Default profile at first run: Standard") |
| MISSION | `Mission.autonomy_profile` [domain-model §7.1; new on the entity] | none (inherit) |
| WORKSPACE | deferred: V1 has one workspace | — |

Profile rules are **unlocked** and carry `source: profile:<name>@<PROFILES_VERSION>`. An explicit
rule beats a profile rule at the same level (§4.2 step 3).

### 5.2 The three profiles [spec; boundary encodings new]

| Class | careful | standard | autonomous |
|---|---|---|---|
| `read`, `web` | ALLOW | ALLOW | ALLOW |
| `write_repo`, `exec` | ASK | AWB `{paths: ['@workspace/**']}` | AWB `{paths: ['@workspace/**']}` |
| `git_commit` | ASK | AWB `{branches: ['archeus/*']}` | AWB `{branches: ['archeus/*']}` |
| `git_push` | ASK | ASK | AWB `{branches: ['archeus/*']}` |
| `install`, `spend`, `deploy`, `external_comm`, `destructive`, `personal_data`, `credential` | ASK | ASK | ASK |

The **built-in floor** (GLOBAL, locked, not a profile, plan §13 spec examples):
`destructive {environment: prod} → DENY`; `deploy {environment: prod} → ASK (locked)`.

`@workspace` is the task's own workspace: its worktree for a project task, the execution's
Archeus-owned directory otherwise (execution-architecture §2, §7). "Autonomous = merge/push to
non-default branches" is encoded as the `archeus/*` task branches, because Core cannot know a
repository's default branch without a repository fact P4 does not record.

### 5.3 What low → high changes, and what it never changes [new, stated as a contract]

Raising autonomy changes **only** which unlocked profile rule answers a class that nothing more
specific answers: `careful → standard` turns workspace writes, workspace execs and task-branch
commits from ASK into bounded ALLOWs; `standard → autonomous` does the same for pushes to task
branches. It **never**:

- loosens a locked rule (the floor, or a user's locked rule at any level) or any DENY;
- overrides an explicit rule deeper than the level the profile is assigned at;
- removes a boundary (every loosening in the table is ALLOW_WITHIN_BOUNDARY, not ALLOW);
- makes an approval reusable across plan versions, or an action approval reusable at all (§8);
- affects the provider-terms gate (§13), routing (§14) or which classes a task may use (§4.4);
- is set by anything but an `admin` user device (`POST /v1/policies/profile`, §18) — the brain
  and the intent pipeline never set it, and a `control` device cannot raise it.

To keep a rule in force under any autonomy, the user locks it. Mission auto-start ("the mission
card asks for confirmation unless the autonomy profile allows auto-start", plan §11 step 4) is
**not** changed in P9: missions keep starting as they do; confirming a mission before `start`
arrives with the mission card (P16). [clar, deferred]

---

## 6. ALLOW_WITHIN_BOUNDARY and match predicates (req. 9)

Natural-language boundaries (the task's `boundaries[]` text, P8) are **never** authoritative.
Authority is a closed vocabulary of typed predicates. [new] (**D3, D4**)

### 6.1 `match` — does a rule apply to this action

`match` is a conjunction over canonical fields: `environment`, `path_glob`, `branch_glob`,
`host_glob`, `command_glob` (argv joined by single spaces), `min_cost_band`. A present key must
hold. **An attribute the action does not carry matches a restrictive rule (ASK, DENY) and never a
permissive one (ALLOW, AWB).** So a plan-level `destructive` item, whose environment is unknown,
meets the floor's `environment: prod` DENY; a permissive rule can never be reached by leaving a
field out. Globs are `fnmatch` over `/`-normalised strings, with `**` crossing directories.

### 6.2 `boundary` — is an allowed action inside its limits

```
boundary = {paths?: [glob], branches?: [glob], hosts?: [glob],
            environments?: [name], max_cost_band?: low|medium|high}
outside  = ASK | DENY            # default ASK
```

- **Containment is conservative.** A path is inside `P/**` iff its literal prefix (up to its first
  wildcard) lies under `P`'s, after normalisation; `..`, an absolute path or a drive letter is
  never inside. A glob that cannot be proven inside is **outside**. A false "outside" costs a
  question; a false "inside" would cost the boundary.
- **Plan stage:** a predicate over an attribute a plan-level item cannot carry (branch, host)
  is **deferred** and recorded as such; the decision stays AWB and the boundary travels with the
  record to P10 (enforcement eligibility) and P11 (capability removal, the hook). A predicate over
  an attribute it does carry must hold: a task whose declared `touches` leave the workspace is
  ASKed about now. An item with no `touches` defers `paths` too.
- **Dispatch / action stage:** every predicate must hold; an attribute that is absent is
  **outside**.
- **Several AWB rules in `effective`** (a deeper AWB and a locked broader AWB): the action must be
  inside **all** of them; outside any, the strictest `outside` applies.

Example (the one the request names): *"allow file modifications within project X, ask outside"* =
`{PROJECT, X, write_repo, AWB, boundary: {paths: ['@workspace/**']}, outside: ASK}`.

### 6.3 `unclassified` actions [spec, rule fixed now]

An action the canonicaliser cannot classify (pipes into a shell, `eval`, decoded payloads) is
evaluated as **every** class the task holds plus `exec`, and the strictest result is taken
(execution-architecture §5). P11 produces the flag; P9's engine and its tests define the rule.

---

## 7. Action identity and `action_hash` (req. 5, 6) — **D7**

### 7.1 Two identities, never merged [clar]

| | What it identifies | Computed by | Covers |
|---|---|---|---|
| `plan.digest` (P8) | the **content** of one plan version: its summary, tasks and their frozen contracts | `validate.digest(plan, tasks)` | integrity of what was planned |
| `action_hash` (P9) | the **exact thing authorised**: this identity, in this plan version, with this content | `actions.action_hash(kind, binding, items)` | what an approval or decision is valid for |

P9 does not re-derive or duplicate P8's digest; it **includes** it.

### 7.2 Definition [new, replaces the P1 function]

```python
binding = {'mission_id', 'plan_id', 'plan_version', 'plan_digest',
           'task_id', 'task_key',        # None for a plan-level subject
           'execution_id'}               # action stage only (P11)
items   = sorted({'task': key, 'action': action.canonical_dict()} ...)
action_hash = sha256(canonical_json({'v': 1, 'kind': 'plan'|'task'|'action',
                                     'binding': binding, 'items': items}))
```

| Included | Why |
|---|---|
| `kind` | a plan approval can never be read as a task or action approval |
| `mission_id` | P1's hash used `plan_version` alone, and `plan_version` 2 exists in **every** replanned mission — an approval for mission A's v2 hashed equal to mission B's v2 for the same action |
| `plan_id` + `plan_version` + `plan_digest` | the exact immutable version: a different version, a superseded one, or content that does not match its digest (recomputed from the rows at every check) is a different identity |
| `task_id` / `task_key` | a task approval covers one task; a different task under the old approval is a different hash |
| `execution_id` | an action approval is for one execution's action (P11) |
| the canonical items | the exact actions, including `paths` / `argv` / `diff_hash` / `environment` |

| **Excluded** | Why |
|---|---|
| **the policy version** | see below |
| harness, account, model, node | resource choice is P10's; a reroute is not a new action, and authorisation must not depend on routing (§14) |
| principal, time, idempotency key | who asks and when are recorded on the decision, not part of *what* |

**The policy version is recorded, not hashed.** P1 (`actions.action_hash(action, policy_version,
plan_version)`), domain-model §9.3 and plan §27 bind approvals to the policy version. P9 keeps the
binding but moves it: every PolicyDecision and Approval stores `policy_version` (a sha256 over the
active rule set, `PROFILES_VERSION` and the engine version), and **every use re-evaluates the
current policy** (§8.4). A policy change that turns an item into a DENY is refused at use; one that
newly requires step-up invalidates an approval given without it; one that loosens needs no
approval. Hashing the version instead would silently invalidate every pending approval on any
unrelated rule edit, with no mechanism in the frozen machines to re-ask — an approval stuck at
PENDING that can never be approved. This is the one place P9 departs from a frozen P1 *document*
rather than extending it, so it is decision **D7** with the alternative spelled out there.

The P1 function and its unit test (`test_domain.py` "policy changed / plan replaced") are replaced
by the new signature and a stricter test: mission, plan id, version, digest, kind, task and each
item each change the hash; policy version and principal do not.

---

## 8. Approvals (req. 4, 8, 11, 19)

### 8.1 Subjects and lifetimes [spec subjects + new `task`] (**D8**)

| Subject | Covers | Requested when | Reusable? | Expiry | Ends |
|---|---|---|---|---|---|
| `plan` | every item of **one** plan version | the plan gate has something to ask | yes — by every dispatch of that version's tasks, for the version's lifetime | 24 h while PENDING [spec]; an APPROVED plan approval does not expire | SUPERSEDED when the version is replaced; REJECTED on reject / request changes / cancel |
| `task` [new] | every item of **one** task of one version | dispatch finds an ASK nothing covers (§12.2) | yes — by that task's retries under the same version | 24 h while PENDING | SUPERSEDED with the version; REJECTED on reject / cancel |
| `action` | **one** canonical action of one execution | the action stage asks (P11 caller) | **no — single-use**: CONSUMED on first use [spec] | 2 h, PENDING or APPROVED [spec] | CONSUMED / EXPIRED / SUPERSEDED |

Other subjects domain-model §9.3 lists (automation enable, knowledge promotion, merge) arrive
with their phases (P14, P16, P13).

**Mapping onto the frozen Approval machine** (state-machines §5, unchanged): `approve`, `reject`,
`ttl_elapsed` (PENDING; APPROVED only for `action`), `plan_replaced` (PENDING or APPROVED, when
the plan version is superseded), `action_executed` (`action` only). A plan or task approval is
never CONSUMED: it is a standing authorisation of an immutable version, not a one-shot token.

### 8.2 When approval is required [spec + new]

- **Plan gate:** exactly when `plan_needs_approval` passes (state-machines §2, unchanged): an item
  is ASK, or the cost band is not known to be under the ceiling. The cost reason is presented as
  such. [spec]
- **Dispatch:** an item is ASK and neither the plan approval nor a task approval covers it
  (§12.2), or the version has no authorisation at all (a plan the P1 stub approved; §21). [new]
- **Action:** the action stage returns ASK and no action approval covers it (P11). [spec]

### 8.3 Remembered approvals [new]

**Never implicit.** "Always allow this" is a **rule**, created by an `admin` device through
`POST /v1/policies/rules` — a separate command the approval card may prefill (P16), never a side
effect of approving. So an approval cannot widen its own scope, and a scope is only ever widened by
someone allowed to write policy. Reuse within a version (plan, task) is the whole extent of it.

### 8.4 Coverage at use [new]

An APPROVED approval **covers** an item at use iff all of:

1. its `action_hash` equals the hash recomputed for this use (same kind of coverage: a plan
   approval covers item *(task, action)* iff that exact item is in its `items`; a task approval
   iff the task and item match; an action approval iff the whole hash matches);
2. the binding is live: the plan version is **in force** (the mission's active plan, state
   APPROVED for dispatch), its recomputed digest equals `binding.plan_digest`;
3. it is not expired, superseded or consumed;
4. the **current** evaluation of that item is ASK (a DENY is never covered; an ALLOW does not need
   covering and does not consume) and, if the current evaluation requires step-up, the approval
   was granted with it.

### 8.5 Eligibility to decide [new] (**D9, D15**)

In the deciding transaction, in this order (the first failure answers; nothing is written):

| # | Check | Failure |
|---|---|---|
| 1 | principal is a `user_device` holding `approve` (application layer; the route's coarse scope is checked first by P3.5b) | `403 not_permitted` (**D22**) |
| 2 | the approval is PENDING, or already decided with the **same** decision | different decision → `422 invalid_transition`; same → idempotent, `changed: false` (§19) |
| 3 | `now < expires_at` | `409 approval_not_eligible {why: expired}` |
| 4 | the request's `action_hash` equals the row's (the `approve` guard, P1) | `422 guard_failed` |
| 5 | step-up satisfied (§8.7) | `422 guard_failed` |
| 6 | binding live: plan in force, digest recomputed and equal, task still in it | `409 approval_not_eligible {why: superseded / digest_mismatch}` |
| 7 | the mission is waiting on this approval (APPROVAL_REQUIRED for a plan approval; BLOCKED on it for a task approval) | `409 approval_not_eligible {why: not_awaiting}` |
| 8 | **approve only**, plan approval: the plan is **current** (§10.2) | `409 approval_not_eligible {why: stale}` |
| 9 | **approve only**: current policy re-evaluated; no item is DENY | `423 policy_denied` (recorded, §9) |

Rejecting (`reject`, `request_changes`) needs checks 1, 2, 4, 7 only: refusing is always safe,
including on a stale or superseded plan.

### 8.6 The approval request (Core/API contract) [spec + new] (req. 8)

`Approval.presented` is built by Core from rows, never from model prose alone (plan §27):

```
presented = {
  what:       [{task, title, class, target, paths, implied_by?, decision, why (rule reasons)}],
  why:        the rules or the cost band that asked, rendered from the matched rules,
  against:    {mission {id, title, objective}, plan {id, version, digest,
               summary (labelled "written by the planner")}, task? {id, key, title}},
  scope:      'this plan version' | 'this task of this version' | 'this one action, once',
  resources:  the capabilities and classes involved; resource choice is left to routing,
  consequences: {approve: 'the plan runs; tasks dispatch under it', reject: 'the mission is
               cancelled', request_changes: 'the mission is planned again', step_up: bool},
  reusable:   'plan-lifetime' | 'task-lifetime' | 'single-use',
  expires_at
}
```

Fields: `id, subject {kind, id}, mission_id, plan_id, plan_version, plan_digest, task_id?,
execution_id?, action_hash, presented, step_up, expires_at, requested_by,
policy_decision_id (the ASK), state` — **all frozen at insert** (`Entity._FROZEN`, P8 D12) — and
the decision fields written once by the deciding transition: `decision, decided_by, decided_at,
decision_note, decided_policy_decision_id`. The API renders it; the SPA's cards are P16's.

### 8.7 Step-up [spec + clar] (**D16**)

`step_up` is set on ASKs for `deploy` and `destructive` [spec]. V1's proof is the device PIN set
at pairing (domain-model §9.3) — pairing is P15, and **every device before P15 is a local device**
(the local token or a launch-code browser, P3.5b). P9 therefore records the requirement and the
guard's `step_up_valid` is *"the deciding device is local, or presented a valid proof"*; P15 adds
paired devices and the PIN. The requirement is never dropped, so an approval granted without it
does not cover an item that needs it (§8.4.4).

---

## 9. The PolicyDecision record (req. 7) [spec + new fields] (**D17**)

One immutable row per evaluation event (not per item): a plan gate decision, a dispatch, an
action. Written in the same transaction as the move it justifies; **every field frozen**
(`FROZEN_ALL` — P9 has no state machine for it, so the writer refuses any update at all).

```
id, stage (plan|dispatch|action), subject {kind, id},
mission_id, plan_id, plan_version, plan_digest, task_id?, execution_id?,
action_hash,                         # of the evaluated identity (§7)
decision,                            # the overall result (strictest over items)
outcome,                             # plan stage: auto_approved | needs_approval | denied;
                                     # dispatch: covered | asked | denied; action: allow|deny|ask
items: [{task, action, decision, effective [rule ids], deciding_rule, conflicts [rule ids],
         boundary?, checks {checked [], deferred [], outside []}, step_up,
         covered_by? (approval id)}],
matched_rules: [full rule snapshots, in precedence order],
cost? {band, ceiling, within},       # plan stage
profiles {user, mission}, estop, principal {kind, id},
policy_version, engine_version,
reason,                              # rendered from the rules, never free text
approval_id?                         # the approval it requested or consumed
```

Everything the request asks it to preserve — what, when (`created_at`), under which policy
(`policy_version`, snapshotted rules), which rule matched (`deciding_rule`, `effective`), result,
scope (`subject`, `binding`), reason, approval, plan version, `action_hash`, boundary and expiry
(the boundary and the checks; the approval's `expires_at`), provenance (rule `source` /
`author_principal_id`, principal) — is on the row, so *why was this allowed / refused* is
answered from it without re-running anything; and re-running it from its own snapshot gives the
same answer (replay test U-P3).

What is recorded [spec, domain-model §9.2]: every plan-stage decision; every dispatch; every
action-stage ASK and DENY and every action-stage ALLOW inside a mission. Archeus's own tool-less
calls are **not** policy-evaluated in P9 (§13), so there is nothing to count for them yet.

---

## 10. Plan-version integrity, stale and superseded plans (req. 5, 11)

### 10.1 Binding [new] — through `action_hash` (§7): an approval or decision names `plan_id`,
`plan_version` and `plan_digest`, and every check recomputes the digest from the rows (the P8
`ready` guard's computation) and compares.

### 10.2 "current" made exact [clar] (**D9**)

P8's plan view has `current`, which is only the **context package's currency**
(`planner.currency`). P8 D11 asked P9 to *refuse to approve a version whose view shows
`current: false`*. The request states the contract as *current: true → potentially eligible;
current: false → cannot be approved / executed*. P9 makes it three exact facts, adds them to the
plan view (`in_force`, `eligible`, `eligible_why`) and leaves `current`'s meaning as P8 built it:

| Fact | Definition | Approve (plan) | Dispatch |
|---|---|---|---|
| **in force** | the mission's active plan, state PROPOSED or APPROVED (never SUPERSEDED / REJECTED) | required | required (and APPROVED) |
| **intact** | recomputed digest equals `plan.digest` | required | required |
| **current** | P8 currency true **and** the event log still reaches back to the package (`outbox.floor(conn) <= package.as_of_seq`; a pruned log is *unknown*, so *stale*) | required | **not re-judged** |

Why dispatch does not re-judge currency: currency goes stale on any `project.changed` or
`architecture.state_changed` in the mission's project, and in P11–P13 **the mission's own tasks**
change the project. Re-judging it at dispatch would deadlock every multi-task code mission on its
own first commit. Freshness during execution is replanning's business (P12/P13 feed checkpoints
and failures back), not authorisation's; authorisation at dispatch is *this exact version, intact,
in force, authorised, under the current policy*. This narrows the request's literal wording and is
therefore decision **D9**.

### 10.3 What happens when …

| Event | Effect |
|---|---|
| a **PROPOSED** plan (approval PENDING) is superseded | same transaction as `superseded` (inside `propose_plan`): every PENDING / APPROVED approval bound to it → `plan_replaced` → SUPERSEDED (**D14**) |
| an **APPROVED** plan is superseded (a replan) | its plan approval and task approvals → SUPERSEDED in that transaction; the new version is decided afresh by the plan gate; nothing carries |
| a task "changes" | impossible in place: a task's contract is frozen with its version (P8 D12); a changed task is a new version with new task ids, so every TASK rule and task approval stays with the old one |
| the digest does not match | refused everywhere (`digest_mismatch`), never repaired |
| the mission changes after approval (its planning inputs) | pending plan approval: the plan is no longer *current*, approve refused (`stale`); the user rejects or requests changes (explicit — P9 starts no replan and spends no model call). Approved and executing: no effect on authorisation (§10.2); later tasks keep dispatching under the version the user approved |

Approval never leaks across versions because nothing an approval covers is shared by two
versions: plan id, digest and task ids differ, and the same-transaction supersession removes it
from the live set before anything could ask.

---

## 11. DENY, ASK, BLOCKED — and refusals that are neither (req. 10)

"Not authorised" and "not understood" never share a path, a trigger, a `planning_blocked` kind or
an error code.

| Case | Class | What the mission does | Code |
|---|---|---|---|
| hard deny (a matching DENY, the floor, e-stop) at the **plan** gate | DENY | `propose_plan` writes nothing (P3.5); the responding command records the PolicyDecision and `planning_blocked {kind: policy, policy_decision_id, round_seq}`; REASONING → BLOCKED via the new `plan_denied` (**D11**); PLANNING / REPLANNING wait in place (P8 D6) | event only (no request is refused) |
| hard deny at **dispatch** | DENY | `dispatch_task` refused before writes (P3.5, unchanged); the next `advance` takes the existing `unrecoverable` and **records the DENY it judged** with that move (**D12**) | `423 policy_denied` to a direct caller |
| hard deny at **decide** | DENY | nothing moves; recorded | `423 policy_denied` |
| policy conflict | resolved (strictest) | whatever the strictest says | — (flagged in the record) |
| missing policy | DENY | as hard deny | — |
| ASK at the plan gate | ASK | APPROVAL_REQUIRED (unchanged) + Approval(plan) | — |
| ASK nothing covers at dispatch | ASK → **BLOCKED** | mission `block` (existing edge), `blocked_reason: authorization`, Approval(task) (§12.2) | — |
| missing authorisation (no decision for an in-force version) | → **BLOCKED** | as uncovered ASK: never proceeds, never denied (nothing forbids it — it was never asked) | — |
| expired authorisation | not an authorisation | re-evaluated as if absent → ASK → a new approval | decide: `409 {why: expired}` |
| stale plan | not eligible | approve refused | `409 {why: stale}` |
| superseded plan | not eligible | approve refused; its approvals already SUPERSEDED | `422 invalid_transition` / `409 {why: superseded}` |
| invalid action hash (decide) | not this action | nothing | `422 guard_failed` |
| principal may not decide | not permitted | nothing | `403` |
| not understood (clarification, challenge) | P7 / P8, unchanged | `planning_blocked` `clarification` / `challenge`, `challenge_raised` | — |

`PLANNING_BLOCKS` gains `policy` [clar]. Leaving a policy block: REASONING's BLOCKED is left by the
explicit `resume` (P8 D6); a policy **rule change** starts a new planning round for a mission
waiting in a planning state with `planning_blocked.kind == policy`, exactly as
`provider_terms.decided` does for `kind == call` (**D24**). REPLANNING has no `cancel` edge in the
frozen machine, so a mission whose replan is denied waits there until policy changes — a P3
limitation recorded, not changed (§27.9).

---

## 12. Authorisation at the gates

### 12.1 The plan gate [spec + new recording]

`Work.propose_plan`'s decision tail is unchanged (P8 D4): `plan_auto_approved`, else
`plan_needs_approval`, over the Policy port, in the recording transaction. P9 adds, **in
`Missions._fire`**, the one place a mission moves (P3.5): when the trigger is a plan decision, the
evaluation the guard **judged** (`judged[-1]`, as `decided_plan_version` already is) is recorded,
and

- `plan_auto_approved` → PolicyDecision(stage plan, `auto_approved`) + plan `approved`
  (PROPOSED → APPROVED, P8-declared, first fired here);
- `plan_needs_approval` → PolicyDecision(stage plan, `needs_approval`) + Approval(plan, PENDING)
  + `approval.requested`.

`Missions.snapshot` builds its per-item context through `authorization.context` instead of the
bare `{mission_id, …}` dict, and evaluates `declared ∪ implied` (§3.3). The facts tuple the guards
read is unchanged in shape.

### 12.2 Dispatch [new] (**D13**) — resolves P3.5 deferral (5)

`Work.dispatch_task` replaces `_refuse_denied` with `authorization.check_dispatch`:

- every item ALLOW / AWB-inside, or ASK and covered (§8.4) → proceeds; the PolicyDecision
  (`covered`) commits with the dispatch;
- any DENY → `PolicyDenied`, nothing written (unchanged); `unrecoverable` records it (§11);
- an ASK nothing covers, or no authorisation → mission `block` + Approval(task) +
  PolicyDecision(`asked`), one transaction; the engine reports `awaiting_approval`. Approving it
  resumes the mission in the same transaction (`unblock` + `redispatch`, `held_from` EXECUTING),
  and the next dispatch is covered; rejecting leaves the mission BLOCKED for the user to cancel.

This is what makes a policy that turns to ASK after an automatic approval ask again, and binds
the dispatch to the policy that allowed it.

### 12.3 The mission `approve` edge becomes guarded [new, P3 table] (**D10**)

`APPROVAL_REQUIRED → APPROVED: approve` is unguarded today — any caller firing it by name
(`Missions.fire`) approves the mission with no approval at all. Guard `approve` (mission): the plan
in force has an APPROVED plan approval whose `action_hash` equals the one recomputed for it.
Only `Authorization.decide` produces that, in the same transaction.

### 12.4 Who may fire which trigger [spec: deferred to P9 by P3] (**D25**)

| Trigger | Fired only by | Principal |
|---|---|---|
| mission `approve`, `reject` (from APPROVAL_REQUIRED), `request_changes` (from APPROVAL_REQUIRED) | `Authorization.decide` | the deciding `user_device` with `approve` |
| mission `plan_auto_approved`, `plan_needs_approval`, `plan_denied` | the plan gate / the denial command | system (planning worker, engine) |
| plan `approved`, `rejected` | `Authorization` | as the mission move it accompanies |
| approval `approve` | `Authorization.decide` | `user_device` + `approve` |
| approval `reject` | `Authorization.decide`; `Authorization.withdraw` when its mission leaves the awaiting state (cancel) | `user_device` + `approve`; system |
| approval `ttl_elapsed` | the policy worker's sweep | system |
| approval `plan_replaced` | the supersession inside `propose_plan` | system |
| approval `action_executed` | `Authorization.evaluate_action` (P11 caller) | system |
| mission `block` for authorisation, and its resume | `Authorization.check_dispatch` / `decide` | system / the deciding device |

A source scan (like P3.5's "one path for a mission move") fails if any other module fires one of
these triggers. `pause`, `resume`, `cancel`, `accept` and `unrecoverable`-as-declaration keep the
P3.5b route scopes (`control`); nothing about them changes.

---

## 13. Provider terms (req. 14) [spec, ADR-0021, unchanged]

Two independent gates that never substitute for each other:

| | ADR-0021 provider terms | P9 policy |
|---|---|---|
| governs | whether a **real harness** may be used headlessly (and rotated) under its provider's terms | whether **Archeus** may perform an action in a context |
| answered by | the user, per harness (`ProviderTerms`) | rules, profiles, approvals |
| checked | at election and immediately before a spawn (P6), and at routing / spawn (P10, P11) | at plan gate, dispatch, action |
| applies to | tool-less calls **and** tool-using execution | tool-using execution only |

- A policy ALLOW never implies provider permission, and `permitted` never implies a policy ALLOW.
  Tool-using execution needs **both** (plan §31.4).
- Archeus's own tool-less calls stay exactly as P6 built them: gated by ADR-0021, read-only and
  ephemeral by construction, **not** policy-evaluated in P9 (plan §31.4: "they need the ADR-0021
  gate but not P9"). The planner being gated still leaves missions `gated` in REASONING (P8 D5).
- P9 has no provider-terms code and no rule can name a provider: provider terms are not an action
  class. A boundary test asserts `core/policy` never reads `provider_terms` (E8).

## 14. Policy vs routing, execution (req. 12, 13)

### 14.1 Routing (P10) [spec + clar]

P9 never chooses a harness, account, model, node or provider, and none of them is an input or part
of `action_hash`. What P9 **gives** P10 is data on the decision record: per item the decision and
boundary, from which P10's enforcement step derives eligibility (resource-router §3: `none` only
for all-ALLOW, `sandbox` for AWB only if the boundary is sandbox-expressible — `paths` yes,
`branches`/`command_glob` no — `hook` otherwise). P9 implements no `allows_resource`: the router's
"policy" step is P10's, reading this record. Resource *restrictions* (a project forbids an account)
are `ResourcePolicy`, P10's.

### 14.2 Execution (P11)

P9 does not spawn, dispatch a process, resume, stop, pause, execute, verify or review. It
authorises, blocks or asks. `dispatch_task` remains P3.5's command that commits an INTENT row; P9
only changes the authorisation check in front of it. The action-stage command exists and is tested
by direct calls; the hook, its token, its route and the halt / resume-with-one-shot-allow flow are
P11's (execution-architecture §5).

### 14.3 The adapter registry gate [spec + clar] (**D20**)

The P9 engine declares `is_stub = False` — the only object that may (plan §31.1 P1). The runtime's
default `Ports.policy` becomes the engine, so the registry's gate *would* now admit a real adapter;
**none is registered**: the runtime registers `FakeHarness` alone, and real tool-using adapters are
P11's (plan P11: "the real policy implementation replaces the stub, which unlocks real adapters in
the registry"). A runtime test asserts the registry holds only the fake harness (E7). `health`
reports the policy port as real (`ports` stops saying `stub` for policy; the P3.5b CLI test that
greps for `ports stub` changes with it).

---

## 15. Persistence (req. 15) — migration `0008_policy.sql` [new] (**D17**)

Same row shape as 0001–0007 (id, promoted columns, `version`, timestamps, audit pair, `body`).

```sql
CREATE TABLE policy_rules (
    id TEXT PRIMARY KEY, scope_level TEXT NOT NULL, scope_ref TEXT,
    action_class TEXT NOT NULL, decision TEXT NOT NULL,
    retired_at TEXT, supersedes_rule_id TEXT REFERENCES policy_rules (id),
    version, created_at, updated_at, created_by, updated_by, body);
CREATE INDEX policy_rules_live ON policy_rules (action_class, scope_level) WHERE retired_at IS NULL;

CREATE TABLE policy_decisions (
    id TEXT PRIMARY KEY, stage TEXT NOT NULL, mission_id TEXT REFERENCES missions (id),
    plan_id TEXT REFERENCES plans (id), task_id TEXT REFERENCES tasks (id),
    decision TEXT NOT NULL, action_hash TEXT NOT NULL,
    version, created_at, updated_at, created_by, updated_by, body);
CREATE INDEX policy_decisions_by_mission ON policy_decisions (mission_id, stage);

CREATE TABLE approvals (
    id TEXT PRIMARY KEY, subject_kind TEXT NOT NULL, subject_id TEXT NOT NULL,
    mission_id TEXT NOT NULL REFERENCES missions (id), plan_id TEXT NOT NULL REFERENCES plans (id),
    task_id TEXT REFERENCES tasks (id), action_hash TEXT NOT NULL, state TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    version, created_at, updated_at, created_by, updated_by, body);
-- at most one live approval per identity: a repeated request finds it (§19)
CREATE UNIQUE INDEX approvals_live ON approvals (action_hash) WHERE state IN ('PENDING', 'APPROVED');
CREATE INDEX approvals_by_mission ON approvals (mission_id, state);
```

- **Single writer, one transaction per command, events in the same transaction** [spec, ADR-0002].
- **Immutability:** PolicyDecision `FROZEN_ALL` (no state: nothing may be updated, ever);
  Approval content frozen, only its state and the once-written decision fields move; PolicyRule
  immutable except `retired_at`, which is written once. Historical decisions are never mutated.
- **Optimistic concurrency:** `expected_version` optional on decide (P2 `409 version_conflict`).
- **No backfill** of authorisations for development databases: a plan the P1 stub "approved" has
  no decision, so its next dispatch blocks and asks (§11 *missing authorisation*) — forging an
  approval for it would be the one thing P9 exists to prevent. V1 is unreleased.
- New entity fields live in `body`: `User.autonomy_profile`, `Mission.autonomy_profile`, the
  PolicyRule / PolicyDecision / Approval fields above. `partial index` needs SQLite ≥ 3.8; the
  floor is 3.31 (P2).

## 16. Events (req. 16) [new] (**D18**)

| Type | Subject | Visibility | When |
|---|---|---|---|
| `policy_rule.created` | policy_rule | user | a rule (or a revision) was written; payload `before`/`after` |
| `policy_rule.retired` | policy_rule | user | a rule was retired; payload `before`, `replaced_by?` |
| `policy_decision.created` | policy_decision | user for DENY / ASK, else system | a decision was recorded (payload: stage, decision, outcome, mission, plan, task) |
| `approval.state_changed` | approval | user | written by `Tx.transition` (approved, rejected, expired, superseded, consumed) — the P1 machine's event, registered now because P9 first moves an approval |
| `approval.requested` | approval | user, notify | [spec, already registered] |

*Approval granted / rejected / expired / authorisation invalidated* are `approval.state_changed`
with their triggers — not four more types. Plan `approved` / `rejected` are the existing
`plan.state_changed`; `plan_denied` the existing `mission.state_changed`; the profile change a
`mission.updated` / `user` event with the field named (**never** a planning input: `autonomy_profile`
is not in `planner.INPUT_FIELDS`, so it neither stales a plan nor starts a round). No automation
event is added.

## 17. Application commands

`archeus/core/application/authorization.py` (`Authorization`), each one writer transaction:

| Command | Does |
|---|---|
| `context(tx, …)` | gathers `ctx` (§3.1); read-only |
| `record_plan_decision` | called from `Missions._fire` for plan decisions (§12.1) |
| `record_plan_denial` | the response to a plan-gate `PolicyDenied`: re-evaluates in its own transaction, records, blocks (§11), ends the planner call (P8's `_end`, same transaction) |
| `check_dispatch` | §12.2 |
| `decide` | §8.5; approve / reject / request_changes |
| `withdraw` | system-rejects the PENDING approvals of a mission leaving the awaiting state (cancel) |
| `supersede_for(plan_id)` | called inside `propose_plan` with the plan's `superseded` move |
| `expire_due(now)` | the sweep |
| `evaluate_action` | action stage: records; ASK → Approval(action); a covered ASK → ALLOW + CONSUMED (P11 caller) |
| `create_rule`, `retire_rule`, `set_profile` | admin commands, with before/after events |
| `simulate` | pure evaluation of a hypothetical action (optionally with hypothetical rules); writes nothing |

`archeus/core/policy/` holds the pure parts: `engine.py` (`PolicyEngine`, `is_stub = False`),
`rules.py` (the floor, the profiles, `PROFILES_VERSION`, predicates, containment). The
`archeus-policy` worker (`core/policy/worker.py`, the `WorldLoop` runner P4 introduced) runs only
`expire_due`; `health.policy` = `{pending, next_expiry}`.

## 18. API (req. 17) [new] (**D19**)

| Route | Scope | Idempotency | |
|---|---|---|---|
| `GET /v1/policies` | observe | — | active rules (built-in, profiles expanded, user), profiles, `policy_version` |
| `POST /v1/policies/rules` | **admin** | required | create a rule (or a revision: `supersedes_rule_id`) |
| `POST /v1/policies/rules/{id}/retire` | **admin** | required | |
| `POST /v1/policies/profile` | **admin** | required | `{scope: user | mission, mission_id?, profile}` |
| `POST /v1/policies/simulate` | observe | — | writes nothing |
| `GET /v1/policy-decisions` (`?mission`, `?stage`) · `GET /v1/policy-decisions/{id}` | observe | — | |
| `GET /v1/approvals` (`?state`, `?mission`) · `GET /v1/approvals/{id}` | observe | — | each with `eligible` / `eligible_why` computed now |
| `POST /v1/approvals/{id}/decide` | **approve** | required | `{decision: approve|reject|request_changes, action_hash, note?, step_up?, expected_version?}` |

The mission view gains `autonomy_profile` and `pending_approval_id`; the plan view `in_force`,
`eligible`, `eligible_why`. **Not added:** any execution, dispatch, routing, hook
(`/v1/hook/evaluate` → P11 with hook tokens) or automation route. The chat verbs `approve` /
`reject` stay `NOT_YET` in the P7 grammar, their message naming P16 instead of P9: a chat verb has
no card to bind the hash to, and the card is P16's (**D19**). Generated `api-reference.md` and
`generated.ts` are refreshed (P3.5b tooling).

---

## 19. Idempotency and concurrency (req. 19)

- **Deciding:** `decide` requires an idempotency key [spec, state-machines §5]. The same key and
  body returns the stored response (P2 writer); the same key with a different body is `409`
  (P2 `IdempotencyConflict`). A **different** key repeating the **same** decision on an already
  decided approval (a double tap from two devices) returns the existing decision with
  `changed: false` — one decision, one authorisation, never two. A different decision is
  `422 invalid_transition`. [new detail, **D15**]
- **Requesting:** at most one live approval per `action_hash` (the partial unique index), so the
  same action asked twice finds the same PENDING row; after an action approval is CONSUMED, the
  next identical action needs a new one (single-use). A different `action_hash` is a different
  approval, always.
- **Concurrency:** the single writer serialises decide against supersession, expiry and dispatch.
  Each re-reads its rows in its own transaction, so the loser sees the winner's state: an
  approval superseded one command earlier is `422 invalid_transition`; a plan replaced between
  display and click is `409 superseded`.
- **Plan decisions** stay once per version (`decided_plan_version`, P3.5).

## 20. Security (req. 18)

Uses the P3.5b model unchanged: device tokens, route scopes, Host / fetch-metadata allowlists,
no tokens in query strings. P9 adds the application-layer principal check (§8.5.1).

| # | Threat | Defence | Test |
|---|---|---|---|
| X01 | replay of an old approval on a new version | hash binds plan id + version + digest; same-transaction supersession | I-A07, M09 |
| X02 | action-hash mismatch / forged decide body | the client echoes the row's hash; the server computes every hash; guard compares | I-A05, M10 |
| X03 | plan-version substitution (approval for v1 used for v2; v2 of another mission) | `plan_id`, `mission_id` in the binding (P1's `plan_version`-only hash collided across missions) | U-H2, M16 |
| X04 | scope escalation (a plan/task approval covering more) | coverage is per exact item; no "remember"; rules only by admin | I-A09, M13 |
| X05 | policy inheritance abuse (a deeper rule or a profile loosening a locked rule) | locked rules always in `effective`; profiles unlocked | U-R4, M04, M23 |
| X06 | stale approval (context changed) | currency at approve, with the retention floor fail-closed | I-A10, M08 |
| X07 | superseded approval | SUPERSEDED in the supersession transaction; binding re-checked | I-A08 |
| X08 | duplicate approval rows | partial unique index | I-A12, M25 |
| X09 | approval replay of a single-use action approval | CONSUMED on first covered use | I-A14, M12 |
| X10 | concurrent approvals from two devices | single writer; idempotent same decision | I-A13 |
| X11 | conflicting policies | deterministic strictest + recorded conflicts | U-R6 |
| X12 | forged client requests (another principal, missing scope, cross-site) | route scope (P3.5b) + application principal check; brain / execution principals can never approve | judge G6, I-A15, M22 |
| X13 | event ordering (acting on an event about a state that moved) | events are ids only; every command re-reads rows in its transaction | I-A16 |
| X14 | the brain approving its own plan | brain principal holds `propose` only; `403` at both layers | judge G6 |
| X15 | an execution asking and answering its own approval | execution principals hold `request_approval`, never `approve` | I-A15 |
| X16 | idempotency key reused for a different decision | P2 `409` | I-A13 |
| X17 | clock games on expiry | Core's transaction clock only; the client sends no time | I-A11 |
| X18 | TOCTOU between evaluation and use | evaluation and the move it justifies are one transaction | I-D1 |
| X19 | a DENY approved anyway | DENY is never approvable (checked at decide, re-checked at use) | I-A17, M01 |
| X20 | autonomy raised from a phone | `admin` only; `control` cannot | I-P6 |
| X21 | rule or decision tampering | rules retire + revise with before/after events; decisions `FROZEN_ALL` | I-S2, M17 |
| X22 | prompt injection through the plan into the approval card | `presented` built from rows; model text labelled and never parsed | U-A2 |
| X23 | leaving out a field to reach a permissive rule | unknown attributes match only restrictive rules | U-R8, M24 |
| X24 | a pruned event log making a stale plan look current | `outbox.floor` check | I-A10b |
| X25 | step-up skipped | recorded requirement, guard, and coverage re-check | U-A3, M28 |

## 21. Acceptance scenarios (req. 20)

### 21.1 Judge (testing-strategy §2) [clar, changes the frozen judge] (**D21**)

- **S5** (row phases `P9` → `P9, P11`):
  - `test_a_plan_that_asks_waits_for_the_user_and_then_runs` — **P9**: passes on a new planner
    recording for *"Ship to prod"* (one `deploy` task; Standard and the floor ASK).
  - `test_deciding_twice_with_one_key_is_one_decision`, `test_a_decided_approval_cannot_be_decided_again` — **P9**.
  - `test_an_approval_is_single_use` — **retagged `phase:P11`**: it needs the fake harness's
    emitted `git push` to reach the action stage twice, i.e. an execution whose tool calls reach
    Core (the P11 hook). Its body is unchanged.
  - **new, P9:** `test_an_approval_does_not_carry_to_the_next_plan_version` — approve *Ship to
    prod*, its task fails (`exit 1`), the replan's v2 asks again; the first approval is
    SUPERSEDED (event) and deciding it again is `422`.
- **G6:**
  - `test_the_brain_principal_can_never_approve` — **P9**; `rig.principal_client` gets its body.
  - `test_a_locked_deny_cannot_be_loosened_by_a_narrower_scope` — **retagged `phase:P11`**: it
    scripts a mid-execution `terraform destroy`, which only the action stage sees. Its objective
    ("Destructive on prod") is deliberately left **without** a planner recording, so it cannot
    pass early for a plan-level reason.
  - **new, P9:** `test_a_locked_deny_cannot_be_loosened_at_the_plan_gate` — a USER-scope `ALLOW`
    for `destructive` is set (**CoreClient gains `set_policy_rule`**, the P4 D1 precedent), a
    mission whose recording plans a `destructive` task ("Destroy the staging database") gets
    `planning_blocked.kind == 'policy'`, no APPROVED plan, and a DENY decision citing the locked
    GLOBAL floor rule.
- Both bindings' `decide_approval` read the approval first and echo its `action_hash` (a client
  that sends what it displayed). The judge's Core runs the real `PolicyEngine` with defaults
  (Standard), in process and over HTTP.
- **Unchanged and must stay green under the real engine:** SK, S1 (both P7 functions, and its
  strict P13 function stays pending), S6's P8 function, S9, S13, S15, SP3, G1, G2, G4, K1–K3, and
  every other currently passing function — their plans are `read`/`write_repo`/`exec` inside the
  workspace, which Standard allows within bounds. A unit test runs every judge recording's plan
  through the plan gate under the default policy and asserts the expected outcome.

### 21.2 P9 scenarios (`tests/v1/unit/test_policy_units.py`, `tests/v1/integration/test_policy.py`, `test_policy_http.py`)

Units (pure engine, `U-`), integration (`I-`), HTTP (`H-`). Every scenario the request lists:

| Req. scenario | Test |
|---|---|
| global allow | U-R1 `read` ALLOW from the baseline alone |
| global deny | U-R2 the floor denies `destructive@prod`; a USER ALLOW cannot loosen it |
| user override | U-R3 USER explicit `git_push ALLOW` beats the USER Standard profile's ASK |
| project restriction | U-R4 PROJECT `write_repo ASK` tightens USER AWB; I-P1 a mission on that project asks, one elsewhere does not |
| task-specific restriction | U-R5 TASK rule `exec DENY` on one task id; the sibling task unaffected; the rule does not survive a replan (I-P2) |
| action-specific restriction | U-R7 implicit TASK contract: an undeclared class at dispatch/action stage asks; `unclassified` takes the strictest |
| inherited policy | U-R9 no MISSION / PROJECT rule → USER applies; none there → GLOBAL |
| conflicting policies | U-R6 two same-depth rules disagree → strictest, `conflicts` recorded, rule order irrelevant (property) |
| ASK | I-G2 plan gate → APPROVAL_REQUIRED + one Approval + `approval.requested` |
| explicit approval | I-A01 approve → Approval APPROVED, plan APPROVED, mission APPROVED, one transaction, decision recorded |
| explicit rejection | I-A02 reject → mission CANCELLED, plan REJECTED; I-A03 request_changes → PLANNING, plan REJECTED, new round |
| ALLOW_WITHIN_BOUNDARY | U-B1 `touches` inside `@workspace` → AWB with `paths` checked, `branches` deferred |
| boundary violation | U-B2 `touches: ['../x']` / absolute → outside → ASK; `outside: DENY` → DENY; U-B3 dispatch stage: absent attribute → outside |
| autonomy levels | U-P1..P3 careful / standard / autonomous tables per class; I-P4 raising a mission's profile changes only unlocked answers; I-P5 the floor under `autonomous`; I-P6 `control` cannot raise |
| stale plan | I-A10 the project changes while PENDING → approve `409 stale`; reject still works; I-A10b pruned log → stale |
| superseded plan | I-A08 request_changes → v2; v1's approval can never be approved |
| approved plan superseded | I-A07 approved v1, task fails, v2 → v1's approvals SUPERSEDED in the supersession transaction; v2 decided afresh |
| plan digest mismatch | I-A06 a plan row whose recomputed digest differs (test writes around the writer) → every check refuses `digest_mismatch` |
| action hash mismatch | I-A05 decide with another approval's hash → `422 guard_failed`, nothing written |
| approval replay | I-A14 an action approval covers once, then CONSUMED; the same action again asks again |
| approval expiration | I-A11 with the transaction clock moved: decide `409 expired`; the sweep → EXPIRED; an expired approval covers nothing |
| duplicate approval | I-A12 the same identity requested twice → one row |
| concurrent approval | I-A13 two devices approve (different keys) → one APPROVED, second `changed: false`; same key different body → 409 |
| provider-terms interaction | I-T1 ADR-0021 `unknown` + policy ALLOW → the planner call is still `gated`; I-T2 `permitted` + policy DENY → the plan is still denied; policy code never reads provider terms (E8) |
| no routing in P9 | E1–E3, E6 |
| no execution in P9 | E1–E3, E5, E6 |
| exact plan-version binding | U-H1/H2 hash changes with every binding field, not with policy version or principal; I-A04 an approval for mission A's v2 never covers mission B's v2 |

Plus: I-G1 auto-approval records the decision and fires plan `approved`; I-G3 DENY at REASONING →
BLOCKED via `plan_denied` with `planning_blocked.kind == policy`, and at PLANNING / REPLANNING
waits in place; I-G4 a rule change re-plans a policy-blocked mission waiting in a planning state;
I-D1 dispatch under an unchanged policy is covered and records; I-D2 a policy turned ASK after
auto-approval blocks the mission and asks for the task, approving resumes it, the retry is
covered; I-D3 a DENY at dispatch ends in `unrecoverable` with the DENY recorded; I-D4 e-stop
armed (`run/STOP` present) denies at every stage; I-S1 `simulate` writes nothing; I-S2 a decision
row refuses any update; I-A15 brain / execution / `control`-only principals `403`; I-A16 deciding
on an approval whose mission was cancelled → system-rejected, `422`; I-A17 a DENY is never
approvable. H-01…H-06: every route's scope, idempotency, `403`/`409`/`422`/`423` codes, and that a
decide over HTTP echoes the hash.

Property tests (`U-P`, stdlib `random`, fixed seeds, testing-strategy §1): rule-order invariance;
adding a locked rule never loosens; adding an unlocked broader rule never changes a decision a
deeper rule makes; replay equality from a record's own snapshot.

## 22. Mutation suite (req. 21) — `tools/mutate_p9.py`, each must be killed

| # | Mutation | Killed by |
|---|---|---|
| M01 | DENY ranked below ALLOW (deny → allow) | U-R2, I-A17 |
| M02 | the plan gate treats ASK as auto (ask → allow) | I-G2, judge S5 |
| M03 | specificity ordering removed (broadest applicable wins) | U-R3, U-R4 |
| M04 | explicit deny ignored (`locked` ignored in `effective`) | U-R2, judge G6 |
| M05 | PROJECT-scope rules not matched (project restriction bypassed) | U-R4, I-P1 |
| M06 | TASK rules and the implicit contract rule ignored (task restriction bypassed) | U-R5, U-R7 |
| M07 | boundary check removed (AWB counted as inside) | U-B2 |
| M08 | currency not checked at approve (stale plan accepted) | I-A10 |
| M09 | supersession of approvals removed (old approval reused) | I-A07, judge S5 new function |
| M10 | the hash comparison removed from the guard (action_hash ignored) | I-A05 |
| M11 | `plan_digest` dropped from the binding | U-H1, I-A06 |
| M12 | CONSUMED not written (approval replayed) | I-A14 |
| M13 | plan-approval coverage by class instead of by item (scope widened) | I-A09 |
| M14 | expiry not checked (expired approval accepted) | I-A11 |
| M15 | `task_id` dropped from the binding (different task under an old approval) | U-H1, I-D2 |
| M16 | `plan_id` / `plan_version` dropped (different version accepted) | U-H2, I-A04 |
| M17 | PolicyDecision not frozen (result changed after recording) | I-S2 |
| M18 | the authorisation path calls the Router port | E6 |
| M19 | the authorisation path calls an adapter's `start` / the engine | E6 |
| M20 | missing policy → ALLOW | U-R10 |
| M21 | e-stop ignored | I-D4 |
| M22 | the principal check removed from `decide` | I-A15, judge G6 |
| M23 | profile rules locked-exempt (autonomy loosens a locked rule) | I-P5 |
| M24 | unknown attributes match permissive rules | U-R8 |
| M25 | the live-approval unique index dropped | I-A12 |
| M26 | the mission `approve` guard removed | I-A18 (fire `approve` by name without an approval) |
| M27 | `record_plan_denial` skipped (denial not recorded) | I-G3, judge G6 new function |
| M28 | step-up not required | U-A3 |
| M29 | dispatch stops re-evaluating (policy turned ASK not asked) | I-D2 |
| M30 | the decided evaluation is not the one recorded (recorded after re-evaluating) | I-G5 (policy changes between snapshot and record in a scripted transaction) |

## 23. Phase-boundary tests (req. 13, 22)

| # | Test | Kind |
|---|---|---|
| E1 | `core/policy/**` and `application/authorization.py` import no `harnesses`, `engine`, `runtime`, `api`, `calls`, `planning.planner`, `claude_sessions`, and no routing, execution, verification, review or automation package | static (import closure) |
| E2 | no call named `route`, `start`, `spawn`, `resume`, `stop`, `pause`, `verify`, `review`, `archeus_call` in those modules | static (AST) |
| E3 | no harness, account, model, node or provider identifier is read or written by them, and none is part of `action_hash` | static + U-H1 |
| E4 | the route table's diff against P8 is exactly §18; no route under `/v1/hook`, `/v1/executions`, `/v1/route`, `/v1/automations` | static |
| E5 | with the engine stopped, approving a plan moves the mission to APPROVED and **nothing else**: no task leaves PENDING, no execution, route decision or process exists | runtime |
| E6 | an autouse spy over every P9 integration test counts calls to `Router.route`, `adapter.start`, `archeus_call`, `Verifier.verify`, `Review.review` **from P9 commands** — zero | runtime |
| E7 | the runtime's registry holds only `FakeHarness`; no real adapter's `start` is reachable | runtime |
| E8 | policy code never reads `provider_terms`; ADR-0021's gate behaves identically with any policy | static + I-T1/T2 |
| E9 | no automation row, event or trigger is written | runtime |
| E10 | the state-machine diff against P8 is exactly the mission `approve` guard and the `plan_denied` edge | static (`states.TABLE` snapshot) |

## 24. S6 / P13 and the P8 regression (req. 23, 24)

**S6** is not modified. Its P8 function (a failed task replans into v2) keeps passing under the
real engine — its plan is `write_repo` in the workspace, Standard AWB — and a test asserts that the
replan's v2 is decided afresh by the plan gate with v1's (auto-approval) decision left intact. Its
two P13 functions stay `phase:P13` with bodies unchanged; the recorded fact that the frozen machine
enters REPLANNING three times for a budget of 2 stands (P8 §23.2). S1's strict P13 function is
untouched. The only judge edits are S5 and G6 (§21.1), and each moves a function to the phase that
genuinely owns it while adding a stronger P9 function in its place — no assertion is weakened.

**P4–P8 stay green** — the full suite, plus these checked explicitly because P9 touches their
paths:

- immutable plans: P9 writes only a plan's `state` (`approved`, `rejected`); `_FROZEN` unchanged;
  a P9 test tries to write any other plan field through each new command and is refused;
- plan digest: P9 recomputes it (P8's function) and never stores its own;
- plan versioning / `round_seq` / supersession: unchanged; approvals supersede *inside* it;
- `planning_blocked`: P8's three kinds unchanged; `policy` added beside them;
- provider terms: P6's gate unchanged (I-T1);
- mission lifecycle: the two §23 E10 changes only; `decided_plan_version` unchanged;
- replan budget: judged before the planner, on the plan in force (P3.5) — a denied replan records
  no version, so it spends no budget (I-G3);
- the P3.5 tests that assert *DENY writes nothing* are narrowed to *no plan, task, execution or
  approval* (the denial's PolicyDecision and block are written by the responding command, **D12**).

---

## 25. Answers to the request, by number

| Req. | Where |
|---|---|
| 1 policy question | §3 |
| 2 hierarchy | §4 |
| 3 autonomy | §5 |
| 4 approval | §8, §12 |
| 5 plan-version integrity | §7, §10 |
| 6 action hash | §7 |
| 7 decision record | §9 |
| 8 ask / approval flow | §8.6, §18 |
| 9 allow within boundary | §6 |
| 10 deny | §11 |
| 11 stale / superseded | §10 |
| 12 routing | §14.1 |
| 13 execution | §14.2, §23 |
| 14 provider terms | §13 |
| 15 storage | §15 |
| 16 events | §16 |
| 17 API | §18 |
| 18 security | §20 |
| 19 idempotency | §19 |
| 20 scenarios | §21 |
| 21 mutations | §22 |
| 22 boundaries | §23 |
| 23 S6 / judge | §21.1, §24 |
| 24 P8 regression | §24 |
| 25 implementation plan | §28 |

## 26. Decision pass

**Outcome: D1–D26 approved**, with these binding clarifications:

- **D7:** `policy_version` stays out of `action_hash`. `action_hash` is the identity of the exact
  action being authorised; `policy_version` identifies the policy a decision was made under and
  is recorded separately. Excluding it must not permit replay across policy changes: every use
  of an approval re-checks the exact hash, plan id/version/digest, scope, the policy in force,
  the relevant rules, the autonomy boundary, expiry and every other invalidation condition, and
  re-evaluates rather than trusting the old approval.
- **D9:** context freshness is an approval-time condition; dispatch re-checks the current
  authorisation and action validity without requiring the historical context package to stay
  fresh, so a mission's own legitimate world changes never invalidate its later dispatches.
- **D10:** no command reaches APPROVED by naming the edge; only a real P9 authorisation does.
- **D11:** a policy DENY is not a clarification or challenge; ambiguity, missing information and
  authorisation denial stay distinct.
- **D12:** a DENY creates no plan, task, execution or approval, but the denial itself is always
  persisted — an auditable historical fact.
- **D21:** execution-dependent S5/G6 behaviour moves to P11 without weakening P11; the new P9
  tests test authorisation directly.
- **Historical invariant:** policy decisions are immutable records; a later evaluation under a
  changed policy is a new decision, and an old one is never rewritten.

The table below is the decision pass as proposed:

| # | Decision | Kind | Recommendation |
|---|---|---|---|
| D1 | Rules live at GLOBAL…TASK; GLOBAL is code only (floor + baseline); **ACTION = approvals only**, never a rule | clar | accept |
| D2 | Precedence: deepest applicable (explicit before profile at a level) ∪ locked broader; strictest wins; same-depth conflict → strictest + recorded; no applicable rule → DENY `policy_missing` | spec + new detail | accept |
| D3 | `match` vocabulary; unknown attributes match only restrictive rules | new | accept |
| D4 | `boundary` vocabulary, `@workspace`, conservative containment, `outside: ASK|DENY` (default ASK), intersection of several AWBs; plan stage defers what a plan cannot carry, dispatch/action stages do not | new | accept |
| D5 | Profiles as rule bundles (§5.2 table), GLOBAL baseline `careful`, USER default `standard`, MISSION optional, two-rule locked floor; set by `admin` only; mission auto-start unchanged (P16) | spec + new encodings | accept |
| D6 | Plan items = declared ∪ implied-by-capabilities; `Action.paths` (additive); implicit locked-ASK TASK contract rule at dispatch/action | new | accept |
| D7 | **`action_hash` = sha256(kind, binding {mission, plan id, version, digest, task, execution}, items) and EXCLUDES the policy version**, which is recorded on decisions/approvals and re-evaluated at every use. Replaces P1's `action_hash(action, policy_version, plan_version)`. *Alternative:* keep the policy version in the hash as domain-model §9.3 / plan §27 say — then every rule edit invalidates every pending approval and P9 needs a new approval edge (PENDING → SUPERSEDED on `policy_changed`) plus a re-ask path | new, **changes P1** | accept (the alternative is coherent but costs a machine change) |
| D8 | Approval subjects `plan` / `task` (new) / `action`; plan and task approvals reusable for their version's / task's lifetime, never CONSUMED, expire only while PENDING (24 h); action approvals single-use, 2 h | new | accept |
| D9 | Eligibility = in force + intact + (approve only) current, with the retention floor fail-closed; **dispatch does not re-judge context currency** (it would deadlock on the mission's own commits); `current` keeps P8's meaning, the view gains `in_force` / `eligible` | clar, **narrows the request's wording** | accept |
| D10 | Mission `approve` becomes a guarded edge (an APPROVED plan approval with the recomputed hash) | new, **P3 table** | accept |
| D11 | New edge **`REASONING → BLOCKED: plan_denied`** (guarded); PLANNING / REPLANNING wait in place; `PLANNING_BLOCKS += policy`. *Alternative:* reuse `challenge_raised` (no table change, but it conflates "not authorised" with "challenged") | new, **P3 table** | accept |
| D12 | A refusal still writes nothing (P3.5); the denial is recorded by the command that responds to it (`record_plan_denial`; `unrecoverable` records a dispatch DENY). P3.5 tests narrowed accordingly | clar, **changes P3.5 wording** | accept |
| D13 | Dispatch re-evaluates; an uncovered ASK or missing authorisation → mission `block` + Approval(task); approving resumes. Existing edges only | new | accept |
| D14 | Approvals are superseded **in the same transaction** as their plan version (not by a consumer of `plan.state_changed`, as P8 D14 worded it) | clar of P8 D14 | accept |
| D15 | Decide: `approve | reject | request_changes`, hash echo required; same decision repeated → `changed: false`; different → 422; reject → mission CANCELLED (the frozen `reject` edge), request_changes → PLANNING; pending approvals of a cancelled mission are system-rejected | new | accept |
| D16 | Step-up recorded for deploy/destructive; before P15 every device is local and local satisfies it; the PIN proof is P15's | new | accept |
| D17 | Migration 0008 (three tables, partial unique index); rules immutable (retire + revise); decisions `FROZEN_ALL`; approval content frozen; no authorisation backfill | new | accept |
| D18 | Events: `policy_rule.created`, `policy_rule.retired`, `policy_decision.created`, `approval.state_changed`; nothing else | new | accept |
| D19 | Routes of §18; `/v1/hook/evaluate` → P11; chat `approve`/`reject` → P16 (their `NOT_YET` text changes); `simulate` included | new | accept |
| D20 | The engine is the runtime's default policy (`is_stub = False`); only `FakeHarness` is registered until P11; `archeus-policy` worker for expiry; `health.policy` | new | accept |
| D21 | Judge: S5 row → `P9, P11`, S5 single-use and G6 mid-execution deny → `phase:P11`; two new P9 functions; `CoreClient.set_policy_rule`; `rig.principal_client` body; two planner recordings; bindings echo the hash | clar, **changes the frozen judge** | accept |
| D22 | A principal that may not act is `403 not_permitted` from the application layer, distinct from `422 guard_failed` | new | accept |
| D23 | E-stop is a gathered input (`run/STOP` exists) and denies every stage | clar | accept |
| D24 | A policy rule change starts a planning round for missions waiting in a planning state with `planning_blocked.kind == policy` (the planning worker's `provider_terms.decided` pattern) | clar, **touches the P8 worker** | accept |
| D25 | The trigger authorization table (§12.4), enforced by a source scan | spec (P3 deferral) + new table | accept |
| D26 | `User.autonomy_profile`, `Mission.autonomy_profile`; the workspace profile deferred | clar | accept |

**Follows from the documents** (recorded, not asked): the four decision values (state-machines
§0); DENY always locked (P1 code); the Approval machine unchanged (state-machines §5); approvals
bound, single-use (action), expiring, superseded on replan, idempotent (ADR-0007, plan §27); the
auto-approve ceiling stays P3.5's fixture until P10 (P3.5 deferral 6); tool-less calls are not
policy-evaluated (plan §31.4); capability removal stays the primary enforcement (ADR-0007, P11).

## 27. Explicit conflicts with frozen P1–P8 contracts

1. **P1 `actions.action_hash(action, policy_version, plan_version)`** and its unit test; domain-model
   §9.3 and plan §27 ("hash(action + policy version + plan version)") — replaced by §7 (D7). The
   frozen hash also collided across missions (`plan_version` alone).
2. **P1 `Action`** gains the optional `paths` (additive; every existing canonical form unchanged).
3. **P1 entities** `PolicyRule`, `PolicyDecision`, `Approval` gain fields (P1 said they would
   arrive with their phase); `User`, `Mission` gain `autonomy_profile`.
4. **P3 table:** mission `approve` guarded (D10); new edge `REASONING → BLOCKED: plan_denied`
   (D11). Diagram, `states._GUARDED`, `guards.GUARDS` and `test_state_tables` change together.
5. **P3.5 "DENY writes nothing"** (state-machines §2, work.py docstring, the P3.5 tests) — narrowed
   to *no plan, task, execution or approval*; the denial is recorded by its responding command (D12).
   P3.5 checkpoint (5) is thereby resolved, as it said P9 would.
6. **P3.5b health / CLI:** `ports` no longer reports `stub` for policy (`test_core_lifecycle` greps
   it).
7. **P7 grammar:** `NOT_YET['approve'/'reject']` text changes from P9 to P16 (D19).
8. **P8:** approvals superseded inside `propose_plan`'s transaction (D14 reworded); the planning
   worker handles `policy_rule.*` (D24) and records denials instead of only ending the call (D12);
   `PLANNING_BLOCKS` gains `policy`; the plan view gains `in_force` / `eligible` while `current`
   keeps its meaning (D9). No P8 validation, digest, versioning, budget or planner behaviour
   changes.
9. **Recorded, not changed:** REPLANNING has no `cancel` edge, so a denied replan waits until the
   policy changes (the same limitation P8 accepted for a blocked replan); S6's two-vs-three
   REPLANNING fact (P8 §23.2).
10. **Frozen judge:** S5's row phases, two retags, two new functions, `CoreClient.set_policy_rule`,
    two planner recordings (D21).
11. **The request's wording "current: false → cannot be executed"** is implemented as *not in
    force / not intact → cannot be executed*; context currency gates approval only (D9).

No P2, P4, P5 or P6 contract changes.

## 28. Implementation plan (after approval)

**Files.** New: `archeus/core/policy/{__init__,engine,rules,worker}.py`,
`archeus/core/application/authorization.py`, `archeus/infra/db/migrations/0008_policy.sql`,
`tests/v1/unit/test_policy_units.py`, `tests/v1/integration/{test_policy,test_policy_http}.py`,
`tools/mutate_p9.py`. Changed: `domain/{actions,entities,states,guards,events}.py`,
`infra/db/rows.py` (promoted columns), `infra/paths.py` (`stop_sentinel()`, read-only),
`application/{commands,work,queries,errors,grammar}.py`, `planning/worker.py`, `engine.py`
(`awaiting_approval`, denial recording on the stub path), `runtime.py` (default policy, worker,
health), `api/{routes,schemas}.py`, generated `api-reference.md` / `generated.ts`, `pyproject.toml`
(package list), the judge (`client.py`, `http.py`, `support.py`, S5, G6, `recordings.json`),
testing-strategy §2 (S5 row), and the docs in place: plan §13 and §31.1 P9, domain-model §7.1,
§9.1–§9.3, state-machines §2, §5, api-and-realtime §2–§3, resource-router §3 (reads the record),
execution-architecture §5 (the action-stage command), ADR-0007 consequences.

**Order.**
1. Domain: `action_hash` (U-H), `Action.paths`, entity fields, the two table changes + diagram,
   guards, event types.
2. Migration 0008, rows, writer freezing (I-S2).
3. `core/policy/rules.py` + `engine.py` — pure; U-R, U-B, U-P, property tests; **mutation-verify
   M01–M07, M20, M23, M24, M28 before anything calls it**.
4. `authorization.py`: context, plan-gate recording, denial, supersession, decide, withdraw,
   expiry, dispatch check, action stage, rules/profile admin, simulate; wired into `Missions._fire`,
   `Missions.snapshot`, `Work.propose_plan`, `Work.dispatch_task`, the planning worker, the engine;
   I-tests; P3.5 tests narrowed (D12); full `tests/v1`.
5. Runtime: default policy, `archeus-policy`, `health.policy`; E5–E7.
6. Routes, schemas, queries, generated docs and client; H-tests.
7. Judge: recordings, CoreClient op, rig, S5/G6 edits, both bindings, traceability.
8. Boundary tests E1–E10; mutation suite M01–M30; full suite (legacy + V1), ruff, SPA `tsc`,
   MkDocs `--strict`, wheel contents.
9. Docs in place; this gate → IMPLEMENTED with its as-built deviations.

**Commit boundaries** (each commit leaves the full suite green; branch
`archeus-v1-rearchitecture` only; `main` untouched; PR #6 stays draft, auto-merge off):

1. `archeus: P9 policy domain and storage` — steps 1–2.
2. `archeus: P9 policy engine` — step 3 (pure engine, profiles, units, its mutations).
3. `archeus: P9 authorization and approvals` — steps 4–6 (commands, wiring, runtime, API).
4. `tests: P9 judge, boundaries and mutation suite; docs` — steps 7–9.

Plus a separate commit for any test-race fix found on the way (the P7/P8 precedent).

---

## 29. As built

Implemented in the order of §28, in the four commits it names:

1. `df56497` archeus: P9 policy domain and storage
2. `542403a` archeus: P9 policy engine
3. `2bd1852` archeus: P9 authorization, approvals, runtime and API
4. tests: P9 judge, boundaries and mutation suite; docs (this record)

Files: `archeus/core/policy/{__init__,rules,engine,worker}.py`,
`archeus/core/application/authorization.py`, migration `0008_policy.sql`, and the changes §28
lists; tests `tests/v1/unit/test_policy_units.py` (U-R, U-B, U-P, property and replay tests),
`tests/v1/unit/test_policy_boundaries.py` (E1–E3, E7, E8, E10, the trigger-ownership scan),
`tests/v1/integration/test_policy.py` (I-G, I-A, I-D, I-P, I-S, with E6's spy on every test),
`tests/v1/integration/test_policy_http.py` (H01–H05), `test_planning.py::test_i27_*` (the
planning worker's denial and policy-change round); the mutation suite is `tools/mutate_p9.py`
(36 mutants).

### 29.1 Deviations from this gate

1. **Dispatch defers what a plan-level item cannot carry (§6.2).** The gate made the dispatch
   stage as strict as the action stage. Dispatch re-judges the same plan-level items the plan
   gate judged — a task's declared paths, never a branch or host — so under that rule every
   Standard `git_commit` and every task without `touches` asked again at its first dispatch.
   The plan and dispatch stages defer; the action stage (P11) demands every predicate. This is
   D9's clarification applied to boundaries: dispatch re-checks authorisation and action
   validity, not facts only the action will have.
2. **The mission's `approve` guard landed in commit 3, not commit 1**, with the authorisation
   that satisfies it; two P3.5 tests that approved by firing the edge by name are exactly the
   bypass D10 closes, so commit 1 could not carry the guard and stay green.
3. **A fifth event type, `user.updated`**, records the owner's default autonomy profile (§16
   named "a `user` event with the field named" without registering it).
4. **A denial of a plan that was never recorded has no `action_hash`.** No plan identity exists
   to bind (D12 writes no plan); the decision names the mission, its round and every judged
   item.
5. **Step-up locality:** a principal counts as local unless one of its devices is a paired
   platform (`ios`, `android`), so a local principal with no device row (the in-process client)
   satisfies step-up exactly as the local token does before P15.
6. **E1 allows `planning.planner` and `planning.validate`**, for `currency` and `digest` (P8's
   functions, reused rather than copied); it still refuses the planning worker, `archeus_call`
   and every later-phase package.
7. **Mutations:** M13 (coverage widened) is killed by a direct test of `_covers`, because a task
   approval is found by its own task's hash *and* covers only its own items — no single edit
   lets another task through, which I-D2 proves behaviourally; M15 therefore removes the task
   from the identity itself; M34 (a version no longer in force still eligible) is the second
   layer behind same-transaction supersession and is killed by I-A08b, which moves a plan out of
   force by another path. M30 is "the recorded result differs from the judged one".
8. **Integration scenarios covered at the unit level:** a project restriction (I-P1) and a task
   rule that does not survive a replan (I-P2) are chain properties of the pure engine (U-R4,
   U-R5; task ids are per version by construction); provider terms (I-T1/T2) are E8's static
   proof plus the unchanged K1–K3 and P6 gate tests.
9. **The SPA's stub banner** ("walking skeleton: fake harness, stub policy") no longer shows,
   because `health.core.ports` reports the policy port and it is real; the e2e test asserts
   its absence. The SPA itself is unchanged.
10. **The engine's stop is `policy_denied`** for a mission waiting on a recorded denial, in any
    state, so the P3.5 stop vocabulary survives the new BLOCKED.

### 29.2 Results

- Full suite (legacy and V1): see the P9 report; the docs-nav test is deselected because of the
  user's untracked `docs/pi-sessions.md` (as in P8), and writer throughput is run separately.
- Judge (both bindings): 89 passed, 60 expected failures (P8: 77 / 68).
- Mutation suite: 36 / 36 killed.
- Ruff, SPA `tsc`, MkDocs `--strict`: clean.

### 29.3 Remaining concerns (for later phases)

- **P11:** the hook's `POST /v1/hook/evaluate` and hook tokens call `Authorization.
  evaluate_action`; the execution's `hook_asked` / `resume_approved` moves and the task's
  `action_needs_approval` are P11's. The canonicaliser supplies `branch`, `host`, `argv` and
  `unclassified`, which the action stage then demands.
- **P10:** the router's policy and enforcement steps read the decision record (per-item decision
  and boundary); the auto-approve ceiling is still P3.5's fixture.
- **P15:** step-up proofs for paired devices.
- **P16:** approval cards, the chat verbs `approve` / `reject`, confirming a mission before
  `start` under `careful`.
- A mission whose replan is denied waits in REPLANNING, which has no `cancel` edge (§27.9).
- Plan approvals expire only while PENDING; an expired one leaves its mission in
  APPROVAL_REQUIRED until the user requests changes or cancels (no automatic replan, no model
  call spent).

**DESIGN_GATE = IMPLEMENTED.**
