# Archeus V1 — Migration Plan and Gap Analysis

Status: **DECIDED** (ADR-0001 strangler, ADR-0019 data ownership). Inventory taken at `main` @
`b778226` (2026-09-23): 91 modules, ~43k lines in `claude_sessions/`, ~16k lines in
`claude_sessions/web/`.

## 1. Strategy: strangler, not big bang

- The new package `archeus/` grows beside `claude_sessions/`. The legacy app keeps shipping and
  keeps its tests green throughout.
- **Migrate data, not conceptual mistakes** (implementation plan, Phase 22). Legacy navigation is
  not preserved for compatibility.
- **Default is reuse.** Working logic is imported through thin seams; code is rewritten only
  where it is coupled to UI primitives or to an abstraction V1 replaces. Every REPLACE/REMOVE
  below states why keeping it is not reasonable.
- The migration convenience never changes the target: if reusing something would put a
  provider concept in the domain or business logic in a client, it is wrapped or replaced.

Classification legend: **REUSE AS-IS** (import unchanged) · **REUSE WITH REFACTOR** (import
after a small seam change) · **EXTRACT** (lift the useful logic into `archeus/`, leave the
legacy module as is) · **REPLACE** (V1 has a different design; legacy stays until retirement) ·
**REMOVE** (retire with the legacy app) · **NEW** (does not exist).

## 2. Gap analysis by subsystem

### 2.1 Foundations and infrastructure

| Current | Class | Reason | V1 home |
|---|---|---|---|
| `config.write_atomic`, `write_json_atomic`, `_ensure_dir` (`.gitignore *`) | REUSE AS-IS | correct, tested, stdlib | `infra/*` imports it |
| `jsonstore` (corrupt ≠ empty, quarantine) | REUSE AS-IS | same rule applies to V1's JSON side files | `infra/` |
| `store`, `paths` (project/transcript paths, encoding) | REUSE AS-IS | needed to read harness transcripts and import legacy data | harness adapters, `legacy/importers` |
| `proc` (`run`, `git`, `spawn_detached`, `kill_tree`, `spawn_terminal`, `remote_url_ok`) | REUSE WITH REFACTOR | add pid **create_time** capture and kill-by-(pid, create_time) for the process registry | `node/supervisor.py` |
| `transcripts.iter_json` (streaming JSONL) | REUSE AS-IS | adapters parse transcripts/stream files | harness adapters |
| `events` (diagnostic JSONL log, dedupe) | REPLACE | V1 events are domain events in SQLite written in the same transaction as state; a diagnostic log cannot be a cursor, audit or trigger source. Kept for legacy diagnostics until retirement | `infra/eventlog` (NEW) |
| `notify` (desktop toasts) | REUSE AS-IS | stdlib, cross-platform, fire-and-forget | `infra/notify/desktop.py` |
| `migrate` (old-name state move) | REUSE AS-IS (legacy only) | unrelated to V1 | — |
| `health`, `diskgc` | REUSE WITH REFACTOR | become automations (scheduled maintenance) with policy | `automation` templates |
| `versions` (self/Claude Code/plugin update) | REUSE AS-IS | update checks are infrastructure; exposed under Control → About | Control |
| `cli.py`, `__main__.py` (statusline fast path) | REUSE AS-IS | statusline stays a harness integration | — |
| SQLite DB, writer thread, outbox, migrations | NEW | no database exists today | `infra/db`, `infra/eventlog` |
| Artifact store | NEW | blobs are scattered under `.archeus/` today | `infra/artifacts` |

### 2.2 Harnesses, accounts, routing

| Current | Class | Reason | V1 home |
|---|---|---|---|
| `harnesses.HARNESSES` registry, `impl()`, `homes()`, `instances()`, CAPS | EXTRACT | descriptors become Harness rows + adapter discovery; the late-bound dotted hooks map to the adapter contract | `harnesses/base.py`, adapters |
| `codex.py`, `pi.py` (read-only transcript/index readers) | REUSE AS-IS | adapters need them for inspect/collect_result | `harnesses/codex`, `harnesses/pi` |
| `config.account_env`, `all_config_dirs`, `get_config_dir` (env > setting > default) | REUSE AS-IS | exact env construction for an account | `node` env builder |
| `accounts.py` (TUI account manager) | REPLACE | UI-only module (menus); V1 account management is API + SPA | Control → Resources |
| `rotate.elect`, `candidates`, `used_pct`, `continue_session`, `offer` | EXTRACT | sticky election → router *affinity*; `continue_session` → checkpoint hand-off; `offer` → approval card | `routing/`, `execution/handoff.py` |
| `quota.is_limit_error`, `is_window_limit`, `note_failure`, `note_limit`, `reason` | REUSE AS-IS | detection and the shared latch are reused unchanged; `worst_window` is **not** used by the router (it reports unknown usage as 0); `preflight`'s prompting (`_ask_tui`, `_ask_gui`, `_job`) is not reused — V1 asks through Approvals | `routing/allocation.py`, `infra/llm` |
| `usage.fetch_usage` + background poller | REUSE WITH REFACTOR | fetch reused; P10 preparation adds a public helper returning `(windows, observed_at, status)` from the poller state and `_extract_windows`; the poller runs inside Core and feeds UsageSnapshots; rendering helpers stay legacy | `routing/usage.py` |
| `models.roster`, `family`, `config.current_model`, `MODEL_EFFORT_FRONTIER`, presets, `advise` | REUSE AS-IS | newest-model-following and effort frontier feed ModelOffers and planner tiers | `routing/`, `planning/` |
| `limit_hook.py` (StopFailure → rotation offer) | REPLACE | V1 detects limits from the execution stream/exit and re-routes in Core | `execution/manager.py` |
| `failover.py`, `gateway.py`, `proxy_base.py`, `omniroute.py` | REUSE AS-IS | provider proxies become *accounts* of kind `provider_proxy`; their guard layering (Host, fetch-metadata reject, bearer) is already right | Resources |
| Router with priority/allocation/explanations | NEW | today: sticky threshold rotation only | `routing/router.py` |

### 2.3 Sessions, execution, planning

| Current | Class | Reason | V1 home |
|---|---|---|---|
| `main.build_launch_command` (pure argv/env builder) | REUSE WITH REFACTOR | the function is reusable as-is, but `main` imports the whole TUI; P11 preparation moves it (and its helpers) into a UI-free module re-exported from `main` | claude_code adapter (interactive) |
| `main.py` TUI loop, `ui.py`, `session_menu.py`, `render.py` | REMOVE (at retirement); `render.py` REUSE | legacy TUI; V1 TUI is a new API client; `render.py` ANSI helpers and `term.py` reused | `cli/tui` |
| `term.py` (the one POSIX/Windows key seam) | REUSE AS-IS | exactly the seam the V1 TUI needs | `cli/tui` |
| `sessions.py`, `stats.py` (scan, parse, cost cache) | REUSE WITH REFACTOR | needed for importing history and for manual-session tracking; the stats cache ladder stays | `legacy/importers`, claude_code adapter |
| `transcript.py`, `flowgraph.py` | REUSE AS-IS | execution tail/inspection views | adapter `inspect()` |
| `plan_execute.py` (`_plan`, `edit_plan`, `optimize_plan_council`, `build_exec_launch`, `run`) | EXTRACT | prompts, council idea and `build_exec_launch` inform the planner and interactive hand-off; the TUI `run()` and file-based plan are replaced by Mission/Plan/Task | `planning/`, `execution/` |
| `gui_api` job runtime (`start_job`, `_JOBS`, `_run_cancellable`, `_gate`, `_install_bridge`) | REPLACE | threads + monkeypatched TUI prompts cannot survive restarts, cannot be audited, and tie domain code to UI; V1 uses Executions, Approvals and outbox consumers | `execution`, `policy/approvals` |
| `memory._claude_stdin` / `_claude_json` (headless structured call, `HEADLESS_MARK`) + the process core of `gui_api._run_cancellable` | EXTRACT (P0.5) | into the UI-free `claude_sessions/llmcall.py`; the legacy functions become wrappers with unchanged behaviour. Core must never import `gui_api`: importing it runs `_install_bridge()`, which monkeypatches `ui` in the importing process | `infra/llm/runner.py` wraps `llmcall`; `brain/calls.py` |
| `context_inject.py` (cross-account and, since 2.8.0, cross-harness transcript hand-off) | REUSE WITH REFACTOR | injection mechanism reused; inside a mission the payload becomes the Core-derived checkpoint, outside one it stays transcript-derived (ADR-0023); the target is any installed `interactive` harness | `execution/handoff.py` |
| `memory.headless_harness`, harness `headless_argv` (pi), `_claude_json`'s prompted-schema branch (2.8.0) | EXTRACT | the harness switch for Archeus's own calls becomes adapter `call()` + the pre-router election (ADR-0022); pi's argv is the pi adapter's `call()` | `harnesses/*`, `infra/llm/runner.py` |
| `main.build_launch_command`'s drop of another harness's model/effort (2.8.0) | REUSE | the vocabulary rule (ADR-0022) the adapters' `resume` and launch keep | adapters |
| `checkpoints.py` (read-only file-history view) | REUSE AS-IS | useful evidence in the inspector (what files the session touched) | inspector |
| `worktrees.py` | REUSE WITH REFACTOR | node-computed paths outside the repo; board logic reused for manual sessions | `node/worktrees.py` |
| `loops.py` (session loops, OS-scheduled loops) | REPLACE | a loop is an Automation (schedule trigger + mission template) with policy; OS schedulers are replaced by Core's scheduler (autostart keeps Core alive) | `automation` |
| `review.py` (AI diff review) | EXTRACT | prompt and diff handling reused by the Review step | `verification/review.py` |
| Mission/Plan/Task/Execution engine, state machines | NEW | no work objects today | `core/*` |
| Verification providers | NEW | today "done" = the session ended | `verification/` |
| Execution node + process registry + e-stop | NEW | | `node/` |

### 2.4 Memory, knowledge, context

| Current | Class | Reason | V1 home |
|---|---|---|---|
| `memory.refresh_memory` unit extraction, `_consolidate`, `forget_pass`, `auto_cycle` | EXTRACT | extraction becomes the model pass of repository inspection; consolidation and forget become knowledge maintenance passes producing proposals | `world/inspection.py`, `knowledge/` |
| memory `graph.json` store (entities, relations, provenance hashes) | REPLACE (store) + migrate data | JSON graph written to two places with implicit schema and no supersession links; V1 stores knowledge in SQLite with explicit lifecycle | `knowledge_items`, `relations` |
| `recall.py` (BM25, tokenisation, relation expansion, token budget, hits log) | REUSE WITH REFACTOR | the scorer reused behind `infra/search/bm25.py` through the P5 `lexical` seam (§3); input becomes knowledge rows | `context/`, `infra/search` |
| `recall_hook.py` (per-prompt injection into interactive sessions) | REUSE (legacy-owned until cutover), then REFACTOR | at cutover the hook asks Core for a context package | harness integration |
| `lessons.py` (extraction, merge, decay, autoapprove) | EXTRACT | lesson extraction/merge/decay logic reused by the learning pass | `knowledge/promote.py` |
| `worklog.py` + hook | REPLACE | V1 history is the event log; worklog entries are imported as history, not knowledge | events |
| `memrules.py` (`.claude/rules` with globs), `conventions.py`, `claude_md.py` blocks | REUSE WITH REFACTOR | these are *harness integrations* writing Archeus knowledge into Claude Code's files; they read from Core after cutover | Resources → Claude Code |
| `ctxaudit.py` (per-turn token floor audit) | REUSE AS-IS | Control → Resources → Claude Code diagnostics | Control |
| `brief.py` (next-step suggestions) | REPLACE | superseded by the digest + brain proposals with provenance | `world/digest.py` |
| `system_prompt.py`, `workspace.py` (provenance manifest) | REUSE WITH REFACTOR | project system prompt → project STANDARD knowledge; manifest → inspection input | `world/` |
| Context engine (levels, package, reasons) | NEW | today recall ranks one graph | `context/` |
| Meeting/decision ingestion | NEW | | `knowledge/ingest.py` |
| Architecture constraints + drift | NEW | | `world/drift.py` |

### 2.5 Repositories and world

| Current | Class | Reason | V1 home |
|---|---|---|---|
| `repos.find_git_repos` (depth 4, submodule/worktree classifier), `state()` cache, `head_branch` | REUSE AS-IS | exactly the repository registration + cheap change detection V1 needs | `world/inspection.py` |
| `connections.build_hierarchy` (import graph: Python AST, C/C#/JS/TS regex) | REUSE AS-IS | the deterministic module graph (EXTRACTED edges); the module is already importable without UI, so it is **not** split; it writes the shared `connections-cache.json` (§5) | `world/inspection.py` |
| `connections.render_html`, `/graph` page | REMOVE (at retirement) | replaced by the World graph view | `clients/app/src/graph` |
| `cluster_spec.py` + generated JS/TS | REUSE for the website only | visual geometry for the site and legacy stage; the V1 client does not use the cluster scene | www |
| Project, Person, Organization, Meeting, Decision, System, Idea objects | NEW | | `world/`, `knowledge/` |

### 2.6 Claude Code configuration managers

| Current | Class | Reason | V1 home |
|---|---|---|---|
| `hooks`, `agents`, `skills`, `skillscan`, `plugins`, `mcp`, `outputstyles`, `ccsettings`, `automode`, `denygen`, `statusline`, `provision` | REUSE WITH REFACTOR | real, working capabilities; they configure *one harness*, so they move under Control → Resources → Claude Code. Refactor = remove module-level `ui` imports so the API can call them (today several import `ui` at module level) | harness detail pages |
| `guard_hook.py` | EXTRACT | pattern for the V1 policy hook; V1 hook is fail-closed for Archeus executions and calls Core | `harnesses/claude_code/hooks/policy_hook.py` |
| `logbash_hook`, `concise_hook`, `minimalcode_hook`, `testfilter_*`, `agentnudge_hook`, `memdirty_hook` | REUSE AS-IS | user-facing harness conveniences; unaffected | — |

### 2.7 Interfaces

| Current | Class | Reason | V1 home |
|---|---|---|---|
| `gui.py` server (`_guard`: Host allowlist, fetch-metadata allowlist, token; CSP) | EXTRACT | guard layering is correct and carries over; server itself is replaced (route table, SSE pools, device tokens, remote host allowlist) | `api/server.py`, `api/auth.py` |
| `gui_api.py` 150 routes | REPLACE | routes are UI-shaped (per page) and polling-based; V1 API is resource-shaped with commands/queries/events. Handler bodies that call domain functions are the reuse path | `api/routes.py` |
| `web/app.js`, `app.css`, `motion.js`, `instruments.js`, `flow.js`, `tour.js` | REPLACE | the V1 IA and interaction model differ fundamentally; the legacy SPA keeps working until retirement. Principles (motion, container queries, one loop, dead-space audits) are carried over | `clients/app` |
| `stage.js` (three.js background scenes) | REMOVE from V1 client | ambient background conflicts with "visualisation must mean something"; the flat graph-scene lineage is kept as a candidate for the optional 3D World view | later |
| `themes.py` palettes | REUSE WITH REFACTOR | hex-first authoring + contrast tests + ANSI derivation reused; palettes become thread tints; skins/worlds not carried | `tokens.json` pipeline |
| `gui_qt.py` shell | REUSE WITH REFACTOR | attach to/start Core via discovery file; load the V1 SPA; keep GPU-on policy and background colour handling | desktop shell |
| `tools/smoke_gui.py`, `tools/shot_gui.py`, `tools/shot_tui.py` | REUSE WITH REFACTOR | point at the V1 SPA; keep floors and mutation-verified audits | `tools/` |

## 3. Legacy seams (the only legacy edits, and when they happen)

Narrow on purpose: extract or add what V1 needs; do **not** restructure code that is retiring.
Verified before writing this table: `memory`, `quota`, `connections`, `proc`, `repos`, `recall`,
`rotate`, `usage`, `models`, `harnesses` all import without loading `ui`, `gui_api` or `main`;
`main`, `claude_md`, `hooks` and `system_prompt` load `ui` at import.

| Phase | Seam | Change | Why |
|---|---|---|---|
| P0.5 | headless runner | new UI-free `claude_sessions/llmcall.py`: `build_headless_args(prompt, model, extra_args) -> (args, env, prompt)` (moved from `memory._claude_stdin`: `HEADLESS_MARK`, `--max-turns 20`, `--disallowedTools Write,Edit,NotebookEdit,Bash`, provider env, budget args) and `run_headless(args, prompt, *, cwd, env, timeout, cancel: threading.Event) -> (rc, stdout, error)` (moved from `gui_api._run_cancellable`: Popen with stdin, watcher that `proc.kill_tree`s on cancel/timeout, on non-zero exit `quota.note_failure` + `events.record`). `_run_cancellable` keeps `quota.preflight` and `_JOBCTX` and calls `run_headless`; `_claude_stdin` keeps its foreground progress UI, `_tls`, `last_call_error`, `last_call_cancelled` | the silent path imports `gui_api`, whose import runs `_install_bridge()` |
| P0.5 | process control | `proc.process_create_time(pid)`; `proc.kill_pid_tree(pid, create_time)` (no-op returning False when the create time differs); `spawn_detached(..., stdin_path=None)` (default keeps `DEVNULL`) | registry, safe kill, prompt-on-stdin for detached processes |
| P0.5 | hook environment guard | `recall_hook`, `worklog_hook`, `memdirty_hook`: return immediately when `ARCHEUS_EXECUTION_ID` is set; `limit_hook`: keep `quota.note_limit`, skip `rotate.offer` | account-level hooks fire in every session on that account, including V1 executions |
| P3.5 | CLI dispatch | `claude_sessions/cli.py` routes the reserved verbs `core`, `status`, `approve`, `pause`, `route`, `estop`, `pair` to `archeus.cli.main` (lazy import after the statusline check); all other verbs unchanged. `core` and `status` work (P3.5b); the other five print `archeus <verb> is not available yet (arrives with P<n>); nothing was done` and exit 2 — `approve` P9, `route` P10, `pause` and `estop` P11 (execution control), `pair` P15 | today unknown verbs fall through to `main.run` |
| P5 | lexical scorer | new model-free `claude_sessions/lexical.py` (stdlib only): `tokens_estimate`, `tokenize`, `STOPWORDS`, `query_tokens`, `idf`, `bm25`, `BM25_K1`/`BM25_B`, moved unchanged out of `recall.py`, which imports every name back | `recall` imports `memory` (the headless call) at module level, so reusing it would put a model in the context engine's import closure |
| P10 prep | usage snapshot | public `usage` helper `windows_snapshot(cfgdir) -> (windows, observed_at, status)` over the existing poller state and `_extract_windows` | the router must distinguish unknown from 0% |
| P11 prep | launch builder | move `build_launch_command` and its helpers to a UI-free module re-exported from `main` (patch targets in tests checked first) | `main` imports the TUI |

Not done: splitting `connections` (unnecessary; risky under this repo's import-by-value bug
class), a `quota.assess` refactor (wrong primitive), splitting `gui_api`, removing
`_install_bridge`, moving the auto-memory scheduler. They retire with the legacy app.

## 4. Data migration (P22)

Importer runs read-only against legacy stores, idempotently (keyed by legacy identity), into a
fresh `archeus.db`; re-running updates, never duplicates.

| Legacy data | V1 entity | Mapping |
|---|---|---|
| Accounts (`settings['accounts']`), homes (`settings['homes']`), provider profiles | Account + ResourcePolicy with the V1 defaults (allocation 80, reserve 10); the legacy `rotate_threshold` (default 98) is recorded on the import report for the user to review, not copied into allocation | `auth_kind` by harness/profile |
| Encoded project folders across all accounts | Project (`legacy_enc[]`, `root_paths` from transcript `cwd`, as `paths.find_actual_path` does) | one project per real path, not per account |
| Git repos under projects | Repository + first RepositoryInspection | via `repos.find_git_repos` |
| `graph.json` entities/relations | KnowledgeItem type ENTITY + Relation | `valid=False` → EXPIRED; `stale` flag kept; relations EXTRACTED when from module edges, INFERRED otherwise; `status: pinned` → pinned |
| Lessons | KnowledgeItem LESSON | pending → CANDIDATE; approved/pinned → CONFIRMED; `confidence`, `sids` → provenance |
| Conflicts in graph | Relation `contradicts` + Attention proposal | |
| Worklog entries | events `legacy.worklog` (history) | not knowledge |
| Session transcripts | Session rows (harness claude/codex/pi) + manual Executions for the last 90 days (configurable) | transcripts stay where they are; artifacts only on demand |
| `.archeus/plan-latest.md` | Mission (state PAUSED if the plan was never launched, COMPLETED otherwise) + Plan v1 | origin `legacy_import` |
| Loops registry | Automation (DISABLED; user re-enables under V1 policy) | cron → schedule trigger |
| Project system prompts, CLAUDE.md user fences (KEEP) | STANDARD knowledge (explicit) | |
| Launch settings (model, effort, permission mode) | project/global defaults + policy profile suggestion | |
| Own-call CLI and model (`headless_harness`, `headless_harness_model`, `extract_model`) | `archeus_call` routing preference, global scope (ADR-0022) | a preference, not a constraint, unless the user marks it required |
| Themes | Appearance thread tint (nearest that passes the ΔE gate) | |
| Events log (`archeus-events.jsonl`) | not migrated (diagnostic) | |

## 5. Data ownership during the strangler period (ADR-0019)

| Artifact | Owner before cutover | V1 behaviour before cutover | After cutover |
|---|---|---|---|
| `graph.json`, lessons, worklog | legacy | imports read-only snapshots on schedule | V1 knowledge is source; legacy memory writers disabled |
| CLAUDE.md managed blocks, `.claude/rules/archeus-mem-*` | legacy | never writes | V1 writes via refactored `claude_md`/`memrules` |
| Hooks in harness `settings.json` | legacy (hook manager) | never edits global settings; V1 executions get hooks via per-execution settings | V1 owns; one installer |
| Accounts/homes settings | legacy | reads | V1 DB is source; legacy settings mirrored read-only for the legacy app until removal |
| Transcripts | harness | reads | reads |
| `<project>/.archeus/connections-cache.json` | **shared** | written through `connections.build_hierarchy` (same function, same atomic write, deterministic content) | shared |
| `~/.claude/archeus-limits.json` (rate-limit latch) | **shared** | read and written through `quota.note_limit` / `reason` so both apps agree an account is limited | shared |
| Legacy account hooks (`recall`, `worklog`, `memdirty`, `limit`) | legacy | stand down inside V1 executions via `ARCHEUS_EXECUTION_ID` (P0.5 guard); `limit_hook` still records the shared latch | V1 owns hook installation |

V1 executions are tagged (`HEADLESS_MARK`, `ARCHEUS_EXECUTION_ID`) so legacy session lists and
auto-memory skip them.

## 6. Retirement gate (legacy GUI/TUI)

The legacy app retires when **every** row is checked against the V1 build (the "judge" for the
legacy surface — a capability checklist, since behaviour parity with a redesigned product is not
the goal):

- [ ] launch / resume / fork / attach a session in any project on any account (manual sessions),
      each harness on its own recorded model and effort (ADR-0023)
- [ ] hand a session off to any installed harness, the source session left intact (ADR-0023)
- [ ] memory/knowledge built with only a non-Claude harness installed, on the harness and model
      the user chose for Archeus's own calls (ADR-0022)
- [ ] account rotation on limit (router fallback) with notification
- [ ] usage per account and window visible (Resources)
- [ ] per-project memory injected into interactive sessions (context package via hook)
- [ ] lessons extracted, reviewed, decayed (knowledge lifecycle)
- [ ] CLAUDE.md blocks and path-scoped rules maintained
- [ ] repositories/worktrees board with diff and merge
- [ ] plan → approve → execute (missions)
- [ ] code review of a diff (review mission template)
- [ ] Claude Code configuration: hooks, agents, skills, plugins, MCP, output styles, statusline
- [ ] provider proxies / failover accounts
- [ ] loops / scheduled work (automations)
- [ ] transcript search
- [ ] update checks (archeus, Claude Code, plugins)
- [ ] desktop notifications
- [ ] TUI covers every destination with keyboard parity

Then: remove `web/app.js` & co., legacy routes, legacy TUI screens, `gui_api` job runtime,
`limit_hook`, `worklog` writer, `brief`, `stage.js` (from the app; the website keeps its scene);
keep modules marked REUSE.

## 7. Rollback

Every phase that touches user data is additive until P22: V1 reads legacy stores and writes only
`ARCHEUS_HOME` (target-architecture §5.1) plus the two shared files of §5. Rolling back = stop
using V1 (stop Core first). To reset V1, remove only the V1-owned entries of
target-architecture §5.1 — `archeus.db` and its `-wal`/`-shm` files, `artifacts/`, `backups/`,
`logs/`, `run/` and `worktrees/` (remove its worktrees with `git worktree remove` first, so the
repositories do not keep stale entries). Only V1's entries are ever removed, by name: the
`ARCHEUS_HOME` directory as a whole is **never** deleted, because the legacy Qt shell keeps its
`cache/` there. **Never** delete `~/.archeus/` either: that is a legacy per-project workdir. The
two shared files of §5 are not reset: they belong to the legacy functions that write them.
After cutover,
`archeus migrate --export-legacy` re-emits legacy formats (graph.json, lessons) from V1 knowledge
for 90 days.
