# T-081 · The other five own calls: no tools, fresh call directory (draft)

Drafted 2026-10-14 by a Claude fork under the owner's "Owner follow-ups" answer (draft only). This is a read-only investigation of D:/archeus-pv20-integration at candidate `6bc0668`, which contains T-060 `aaddefd` and T-069 `cece71d`. It used `git`/`grep`/`sed` only. No code was edited, no test was run and nothing was committed. Line numbers are from `6bc0668`.

## 1. What an own call gets today

All five calls go through `OwnCalls.run` (`archeus/core/calls.py:70`) into `CallSpec(workdir=..., no_tools=...)` (`:130-132`).

- **Claude Code** (`harnesses/calls.py:86-110`):
  - `claude -p --max-turns 20 --disallowedTools Write,Edit,NotebookEdit,Bash` (`claude_sessions/llmcall.py:28-29`, `build_headless_args`).
  - Every other tool stays available: Read, Grep, Glob, WebFetch, WebSearch and Task.
  - `--tools ""` is added only when `no_tools` is set (`:92-95`).
- **pi** (`:136-152`):
  - `--tools read,grep,find,ls`.
  - A `no_tools` call is refused as `failed` before it is spawned (`:140-144`). It has no `no_tools` capability (`:128`).
  - Since T-069, the router eliminates pi before selection for a `no_tools` call.
- **Environment:** `config.account_env(home)` is `os.environ.copy()` plus the account selector (`claude_sessions/config.py`). So `ARCHEUS_HOME`, when set, is inherited. That is T-053 P6's second clause, and it is out of this card's scope (see §5).
- **Working directory:** `paths.archeus_home()`, Core's state root.
  - It holds `archeus.db`, `artifacts/`, `repos/`, `worktrees/` (execution workdirs, execution-written content), `run/` (including `run/local-token`, the Core API bearer secret, `archeus/api/auth.py:10`), `logs/` and `backups/` (`infra/paths.py:30-31`).
  - The knowledge pass alone moved to `paths.fresh_call_dir` (T-060 r1, `passes.py:197`).

A read tool in that directory can therefore read Core's database, the local token and every execution's worktree. WebFetch/WebSearch give the same call a way out. This is the surface the owner closed for the knowledge pass ("Knowledge pass gets no tools", T-060), and the reason T-060's GAPS r1 names this follow-up.

## 2. The five calls

"Influenced" means the prompt carries text that an execution, a model or an outside party wrote. That text can try to steer a call that has tools.

| Call | Site (call / workdir) | Purpose / harness flags | Prompt input (all inline?) | Influenced content in the prompt | Reads anything with tools by design? |
|---|---|---|---|---|---|
| decisions | `knowledge/passes.py:214` / `:221` | `knowledge_extraction`, no `no_tools` | yes: `DECISIONS_PREFIX` + meeting name, date and the full notes artifact (`:211-220`). `context_package_id` is recorded, not put in the prompt | meeting notes (imported or user-supplied, outside text) | no. "Read these meeting notes" refers to the text below |
| lessons | `knowledge/passes.py:247` / `:250` | `lesson`, no `no_tools` | yes: mission title and objective, plan summaries, attempt exit reasons, verification and review states (`:238-246`) | plan summaries (planner output), exit reasons | no. "From what is recorded about it below" |
| brain | `missions/intent.py:133` / `:137` | `brain`, no `no_tools` | yes: `brain.prompt(msg.text, lines, answering)` (`core/brain/intent.py`). Context lines come from `brain.describe(conn, pkg)` | user message, knowledge-item summaries (knowledge-pass output from repository facts, so execution-influenced after a merge) | no. "Refer to things ONLY by the handles in brackets below"; answers cite handles |
| planner | `planning/worker.py:128` / `:133` | `planner` (tier `large`, `CALL_TIERS`), no `no_tools` | yes: `planner.prompt(m, lines, replan=...)`. `planner.describe` writes project, inspection (test/build commands), repository constraints and knowledge items as handle lines (`planning/planner.py:120-155`) | inspection facts, knowledge items, prior plan/replan reasons | no. "Refer to things ONLY by the handles"; `touches` globs are relative to the repository, which the call's cwd is not today anyway |
| review | `verification/worker.py:408` (and the `:411` retry) / `:407` | `review`, no `no_tools` | yes: `reviewer.prompt(conn, m, diff)` (`verification/reviewer.py:41-79`): objective, requirements, criteria, tasks, verification results, agent CLAIMs (execution summaries, up to 500 chars each), and numstat only (paths and line counts, at most 80) | **agent CLAIMs, written by the execution itself**, plus changed paths | no. And for a guarded mission the diff is withheld on purpose (`worker.py:397-401`), "withheld, not empty"; a Read tool in ARCHEUS_HOME can open the mission worktree under `worktrees/` and undo that |

None of the five prompts names a file, gives an absolute path to read, or asks the model to look anything up. Each schema answer is built from what is in the prompt; the checks (`check_decisions`, `check_lessons`, `brain.check`, `planner.check`, `reviewer.check`) validate against the prompt's own facts and handles. The `planner.describe` repository path (`p.root_paths`, `r.path`) is the only absolute path in any prompt. It is a label, and it is outside the cwd. Whether Claude Code's Read in `-p` mode reaches an absolute path outside the cwd without a permission prompt was not checked (UNVERIFIED). Inside the cwd, ARCHEUS_HOME, it does.

## 3. What would change with `no_tools=True` and `workdir=paths.fresh_call_dir`

- **Claude Code:** `--tools ""`, a single answer with no tool turns. The same form was run once against the real CLI with `--json-schema` on T-060 (success, owner-authorized). Nothing in the five prompts needs a tool, so the expected change in output is none. That is an expectation, not a measurement.
- **pi:** T-069 removes pi from selection for every one of the five calls.
  - If Claude Code is available on any eligible account, the router picks it. The calls already run on Claude when it is preferred; pi is elected only by preference, or when Claude is out of allocation, health or terms.
  - **On a pi-only Core** (no Claude login, Claude disabled, or every Claude account limited), all five calls end `unavailable` ("no eligible harness"). Today they run on pi with read tools.
  - For the brain and the planner, that is the whole conversation and planning loop. The brain declines the message. The planner records `call:unavailable` and the mission waits in its planning state; `_retry_gated` re-plans only `planning_blocked.kind in ('call', policy)`, so whether it re-plans when an account frees up was not checked.
  - This is the same regression T-060 + T-069 accepted for the knowledge pass, now applied to the core loop. Owner question 1.
- **Review:** with `no_tools`, a guarded mission's withheld diff is actually withheld. An unguarded review judges on numstat plus verification results, which is what its prompt already says it judges on.
- **Directories:** five more call types each leave one `run/calls/<rte id>` per spawned call, kept forever (T-060's keep-all GAP). Brain and review run often, so this is one directory per message read and per review.
- **Static test:** `tests/v1/integration/test_deputies.py` `test_every_own_call_runs_in_a_core_owned_directory`:
  - `FRESH` is one `(file, function)` pair today; it becomes the six.
  - `assert named == {FRESH}` becomes the set.
  - `_core_owned(paths.archeus_home())` stays accepted for any future call. Alternatively it is removed so that `archeus_home()` as a call cwd fails: owner question 2.

## 4. Recommendation per call

| Call | Recommendation | Why |
|---|---|---|
| review | **no_tools + fresh dir now** | Highest risk. Its prompt carries the execution's own CLAIM text. Tools also defeat the guarded-mission withholding. |
| brain | **no_tools + fresh dir now** | Handle-only by design; knowledge summaries in its context are execution-influenced. Pi-only Cores lose it (Q1). |
| planner | **no_tools + fresh dir now** | Handle-only by design; inspection and knowledge facts are execution-influenced. Pi-only Cores lose planning (Q1). |
| lessons | **no_tools + fresh dir now** | Fully inline; the influenced text is plan summaries and exit reasons. |
| decisions | **no_tools + fresh dir now** | Fully inline. The notes are outside text (an imported meeting), the classic injection shape. |

No call needs prompt inlining first: every one already receives all its input in the prompt. None has a reason to keep tools.

## 5. Risks and limits

- **Pi-only Cores** lose all own calls until a pi form meaning "no tools" is verified (`harnesses/calls.py:128`). T-069 makes that a clean `unavailable` rather than a `failed` spawn, and does not fix it. Verifying a pi no-tools flag needs the real pi CLI, which has never been run for this (T-060 notes).
- **Environment:** the call still inherits Core's environment, including `ARCHEUS_HOME` when set (`config.account_env`). With no tools, the model cannot act on it. A hook or settings file that Claude Code loads still could, but in a fresh empty directory under `run/calls/` there is none to load. T-053 P6's environment clause stays a separate item.
- **Unverified:**
  - whether Claude Code reads settings or CLAUDE.md from directories above its cwd (`run/calls/`, `run/`, ARCHEUS_HOME). Core owns them and they hold none today (T-060 GAP);
  - whether `--tools ""` also disables Task/subagent spawning. With no tools listed, none should exist, but it was not checked separately.
- **Out of scope:** interactive sessions Archeus launches (P12, `core/sessions/service.py`), Core Git, verification commands (T-053 O6 list).
- **Integration:** `knowledge/passes.py`, `missions/intent.py`, `planning/worker.py`, `verification/worker.py` and `test_deputies.py` are shared.
  - `verification/worker.py` is also edited by T-062 (in progress on the T-072 candidate) and T-080 (sites `:47-48`, `:296`, `:330`, not `:407`).
  - The edit here is one keyword argument per site, so overlap is textual only.

## 6. Proposed card

```
### T-081 · The other five own calls run with no tools in a fresh call directory
owner: claude · status: proposed
auth: —
scope: Detached checkout from the T-072 candidate (6bc0668, carries T-060 aaddefd + T-069 cece71d) or its successor. archeus/core/knowledge/passes.py (decisions :214-221, lessons :247-250), archeus/core/missions/intent.py:133-137 (brain), archeus/core/planning/worker.py:128-133 (planner), archeus/core/verification/worker.py:403-411 (review, both calls share `ask`): each passes no_tools=True and workdir=paths.fresh_call_dir; tests/v1/integration/test_deputies.py (FRESH becomes the six calls; per-call assertions as for the knowledge pass); per-call integration tests in the existing files (test_knowledge.py, the intent/planning/verification integration files) where a fake caller records the spec. No harness, router, paths.py or canonical document change.
refs: .collab/T-081-own-calls-tools.md; T-060 (pattern, owner answers "A: move it out", "Knowledge pass gets no tools"); reviews/T-060-e95bd2d.md; T-069 (no_tools capability before selection); T-053 section 2 O6 and P6.
accept: (1) every own call (knowledge, decisions, lessons, brain, planner, review incl. the unforbidden retry) is made with no_tools=True and a fresh empty run/calls/<rte id> cwd, never ARCHEUS_HOME or a repository; (2) the static test fails if any own call names paths.archeus_home() or omits no_tools (per owner answer to Q2); (3) with only a pi caller registered each call ends unavailable at routing with nothing spawned and no directory made, and the brain/planner/review record that outcome as today's unavailable paths do; (4) with a fake Claude-capable caller the five produce the same recorded results as before on the existing fixtures; (5) a guarded mission's review prompt still withholds the diff and the call has no tools.
verify: Fake callers only (no real CLI): spec capture per call (no_tools, workdir == call_dir(rd), dir empty and fresh); pi-only routing per call; existing knowledge/intent/planning/verification/deputies suites pass unchanged except the asserted workdir/no_tools; ruff, no CR. Mutants: each call drops no_tools; each call back to archeus_home(); review's retry path keeps tools; static test accepts archeus_home().
commits: —
review: —
notes: Drafted by Claude from T-060 GAPS r1. Owner questions in the note section 7. Behaviour change: a Core with only pi eligible loses the brain, planner, review, lessons and decisions calls (today they run on pi with read,grep,find,ls) until a pi no-tools form is verified. ARCHEUS_HOME in the call environment (T-053 P6 second clause) is not addressed here.
```

## 7. Owner questions

1. **Pi-only Cores.** With `no_tools`, a Core whose only eligible harness is pi can no longer run the brain, the planner, the review, lessons or decisions.
   - **A (recommended):** accept it, as for the knowledge pass. The calls end `unavailable` with a reason. A pi no-tools form is verified later on its own card, with an owner-authorized real pi call.
   - B: give brain and planner `no_tools` only when a no-tools harness is eligible, otherwise pi with read tools. This keeps the loop alive, but it keeps exactly the surface this card closes.
   - C: hold this card until pi's no-tools form is verified.
2. **The static gate.**
   - **A (recommended):** `paths.archeus_home()` stops being an accepted own-call cwd, so a sixth call cannot land there by default.
   - B: keep accepting it and only list the six fresh calls.
3. **One card or two.**
   - **A (recommended):** all five in one card. It is the same two-argument change per site, under one static test.
   - B: review first, alone, because it is the call with execution-written text and the withheld-diff bypass; the other four after.
