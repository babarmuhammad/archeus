# LE-2: mission, project and repository context (2026-10-05)

**Result: the context problem is mostly a display and join problem, not a data problem.** V1 Core
already records most of what makes a running mission meaningful (project, branch, commit, working
directory, task, verification). Almost none of it reaches the screens where people look. Three
facts are not recorded at all: the remote/provider/owner, the current operation inside a task,
and (on the approval record) the target environment. Nothing in this record was implemented in V1
or Core.

> **LV2-1 corrections (2026-10-05)**, checked against the code by the W4 gate drafts and re-read by
> hand (the old rows below are kept, struck through where wrong):
> - *(T-11)* Core runs every execution at `Project.root_paths[0]`, in a task worktree under
>   `ARCHEUS_HOME\worktrees\<project>\<mission>\<task>` on `archeus/<mission>.<task>`
>   (`core/execution/manager.py:280-304`), so "the workdir lies under `Repository.path`" never holds.
>   A mission's repository is derivable only as *the repository at the project's first root* (as the
>   verifier resolves it, `verification/evidence.py:29-32`): **within one project, the repository
>   never tells missions apart in V1.** The fixture's workdirs now have V1's shape.
> - *(T-10)* `Repository.default_branch` is declared and never written (`entities.py:295`), so
>   "Into main" is **not recorded**, not derived.
> - *(T-12)* No repository inspection reads remotes; only `LocalNode.git_remotes`
>   (`node/local.py:230-242`) does, per hook request, keeping the host.
> - *(T-13)* `Approval.items` keeps the full canonical action (environment, branch, host) and is
>   served; only `presented.what` drops it; plan and task approvals carry no environment.
> - *(T-4)* Check output is stored unredacted and content-addressed, reported only as available,
>   and **served by no route**: new **DR-8**.
> - DR-2 must **strip credentials** from any remote URL before it is stored or shown.
> The five gates are drafted in `docs/architecture/lv2-dr{1,2,3,4,8}-*-gate.md` (not implemented).

Lab: `lab/ia.html` (`?ctx=v1`, the default, shows only what V1 records; `?ctx=proposed` adds the
data requirements below, each marked *proposed*). Fixture: `lab/fixture.js`, shaped like V1's own
reads. Inventory: a read-only pass over `archeus/` and `clients/app/src/` with file:line
citations, spot-checked by hand (`queries.py`, `live.py:60-80`, `present.ts:145-153`,
`Work.tsx:100-112`, `entities.py:266-291, 720-732, 975-992`).

## 1. What V1 knows, where it shows, where it is lost

K = a Core field; API = reaches an HTTP read; UI = rendered by the SPA.

| Fact | Core (K) | API | UI today | Lost where |
|---|---|---|---|---|
| Mission title | `Mission.title` | ✓ | Rows, inspector, approval card, toast | — |
| Goal / objective | `Mission.objective` (+ desired outcome, criteria) | ✓ | Inspector Outcome tab only | Never on a row; `presented.against.mission.objective` never rendered |
| Project name | `Project.name`; `Mission.project_id` (nullable) | Missions, attention and digest carry **only the id** | World project page only; the mission inspector shows a bare "project" link | Never joined onto a mission, attention item or digest |
| Repository | `Repository{path, kind repo/submodule/worktree, default_branch, last_revision}` | path, kind, last_revision (`default_branch` undeclared) | Project page section titles | A mission has **no repository link** (only `project_id`) |
| Remote / provider / owner-repo | **Not modelled.** `domain-model.md:166` specifies `remote_url`; it was never built. `LocalNode.git_remotes` reads the host live for boundary checks and keeps nothing | — | — | Never recorded |
| Branch | `Mission.integration_branch` (`archeus/<id>`), `Execution.branch` | ✓ (Execution via open fields) | Collapsed Details of the inspector | Not on rows; `Execution.branch` never rendered |
| Commit / ref | `Mission.integration_head`, `integration_base`, `Verification.revision`/`base_revision` | head declared; base undeclared | Details only | `integration_base`, `base_revision` never rendered |
| Working directory | `Execution.workdir`, `Session.cwd` | open fields; `LiveItem.workdir` undeclared in the generated TS | **Never rendered** (no `cwd`/`workdir` in any `.tsx`) | Everywhere |
| Current task, step N of M | `Task{title, key, state}`; `LiveItem.task_title` | ✓ (`/v1/status` live, plan) | Inspector header only: `statusLine(m, tasks)` | **Rows call `statusLine(m)` without tasks, so the row status line is always empty** on Now and Work (`Work.tsx:107`, `present.ts:149-152`). `live[].task_title` and `live[].waits_on` are fetched on every status read and never shown |
| Current operation (the tool call inside a task) | Not recorded (needs P21's activity record) | — | — | — |
| Verification | `Verification{state, checks[], criteria[], revision, workspace, performed_by}` | ✓ | Evidence tab, inspector detail | Not on rows; `criteria[]` results, `performed_by`, `workspace` never shown |
| Local / remote | `ExecutionNode.kind` exists but V1 never writes a node (`LocalNode.id = None`) | — | — | Derivable: V1 runs only on the local node |
| Target environment | `Action.environment`; policy rules match `environment: prod` | **Dropped**: `presented.what` keeps class, target, paths only (`authorization.py:315-318`) | The approval card shows Class and Target | Known at the action, lost at the approval record |
| Elapsed time | `Execution.started_at`/`ended_at`; events carry `at` | ✓ | Coarse `ago(updated_at)` on rows | No running duration anywhere |

## 2. Known, derived, unknown — the rule the prototype implements

Every context fact the lab renders is one of four kinds, and says which (`context()` in `ia.js`):

| Kind | Rendering | Examples in the lab |
|---|---|---|
| **Known** — a Core field, shown as is | Plain | project, branch, commit, working directory, verification |
| **Derived** — computed from known fields, by a stated rule | A dotted "derived" caption whose tooltip states the rule | repository (workdir under `Repository.path`, or the project's only repository), "into main" (`default_branch`), "on this computer" (V1 has only the local node), step N of M, elapsed |
| **Proposed** — would need a data requirement (§3) | Shown only with `?ctx=proposed`, with a dashed "proposed" caption naming the requirement | remote and provider, environment on the approval, current operation |
| **Unknown** — not recorded | Never a placeholder per field. One quiet line at the end of the context block: "Not recorded by Core: remote, environment." | the same facts in `?ctx=v1` |

**Rows carry one line of context: project · branch, known facts only.** On the phone, the project
name only; the branch is one level down. No badge per fact. The full context block lives in the
peek, the decision page and the mission page (on the 1,700 px composition it moves into the
evidence inspector and appears once).

Two honesty corrections the prototype forced on its own first draft (both now fixed in the lab):

1. **The approval consequence must come from the record.** The first cut said "deploys to staging"
   and "changes 14 files". Core records neither on the approval: the environment is dropped
   (DR-4) and the file count is the planner's own prose. The row now says "3 tasks · includes a
   deploy · expires in 8 min", built from `action_class` and the plan's task count; "deploys to
   staging" appears only under `?ctx=proposed`.
2. **A because-chain hop must be a recorded fact.** The first cut had a third hop ("the
   down-migration drops a column…"). That is a model's reading of the check output, not a
   Core fact. The chain now stops at the failed check, which the Verification record holds.

## 3. Data requirements (documented, not implemented)

Ordered by value over cost. None changes a Core contract in this phase; each needs its own design
gate when a later-V2 phase wants it.

| Id | Requirement | Layer | Size | Unblocks |
|---|---|---|---|---|
| **DR-1** | Join the project **name** onto mission, attention-item and digest reads (or let the client join `/v1/projects`, which it can do today) | API read shape only | Small | Context on every row; Missions grouped by project |
| **DR-2** | `Repository.remote_url` (already specified in `domain-model.md:166`), persisted from the inspection that already reads `git remote -v`; provider and owner/repo **derived** from it, never stored separately | Core field + inspection | Small | "GitHub · owner/repo" in context; links out |
| **DR-3** | A mission's **repository**: either `Mission.repository_id` or a documented derivation rule (the execution's workdir under a repository path). Today a project with two repositories cannot say which one a mission works in | Core field or rule | Small–medium | Repository on multi-repo projects (the lab's `invoicing` shows "repository: not recorded") |
| **DR-4** | Keep `Action.environment` (and branch, host) in the approval's `presented.what` | Core record shape | Small | "Approve and deploy **to staging**" — the consequence in words |
| **DR-5** | `LiveItem` fields in the generated TS types (`workdir`, `branch`, `task_title`, `waits_on`); fix the row status line so it receives tasks | Client only | Trivial | Q1 "what is it doing" on a row (this is a V1 defect, recorded for V1's own follow-up, not fixed here) |
| **DR-6** | The current **operation** inside a task (the latest tool call, in words) | P21 activity record | Owned by P21 | "pytest … run 31 of 50" |
| **DR-7** | A **per-day** event read: `/v1/events?since=&until=&project=` (today: `after` and `limit` only) or a day aggregate | API | Small | The day's light (LE-3, LQ-8) |

## 4. What the user sees with V1 data alone

At `?ctx=v1` the running row reads **"Fix the flaky date test · Run the date suite 50 times · step 4
of 7 · 20 min"** with **"archeus · archeus/m-4c1e · on this computer"** underneath, and the mission
page adds repository, working directory, commit and verification. Every word of that is a V1
Core fact or a stated derivation of one. The only things missing are the remote, the operation
inside the task and the environment, and the screen says so in one line rather than inventing
them. **The prototype therefore needs no Core change to deliver most of the context the brief
asks for; DR-1, DR-4 and DR-5 are the cheap ones that would make it complete.**

## 5. Open

- Human check: is one line (project · branch) the right density on a row, or does the branch
  belong only one level down on desktop too?
- DR-3's choice (field vs rule) needs a Core design decision.
