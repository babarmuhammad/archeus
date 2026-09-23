# External References — Archeus V1 Design Research

Internal document (excluded from the published manual). Every entry uses the external-source
format Archeus V1 itself will store as REFERENCE knowledge
([../architecture/context-and-knowledge.md §7](../architecture/context-and-knowledge.md)):
source URL, inspected_at, source revision, observations, design area, confidence, status.

Evidence labels: **[V]** verified in source at the pinned revision; **[D]** stated in the
project's own docs, not checked against code; **[S]** secondary source; **[I]** interpretation.
Nothing was cloned, built or run; repositories were read through the GitHub API and raw files.

---

## R1 — Munder Difflin

| Field | Value |
|---|---|
| URL | https://github.com/chaitanyagiri/munder-difflin |
| Revision | `c7c8921f4491104d342861e32fa214e486442304` (2026-09-17) |
| Inspected | 2026-09-23 |
| License | MIT (+ separate asset license) |
| Stack | TypeScript, Electron, React, Pixi.js, xterm.js, node-pty, SQLite |

| # | Observation | Evidence | Area | Confidence | Status |
|---|---|---|---|---|---|
| 1 | On-disk hive: shared `registry.json`, `board.md`, `tasks.json`, `log.jsonl`; per-agent `identity.md`, `memory.md`, `inbox/`, `outbox/`, `cursor.json`; `spawn-requests/` queue | [V] `src/main/hive.ts` | State, Event system | high | adapted (single writer + router + cursors, in SQLite) |
| 2 | Single committer: only `commit()` runs git; retries; stale lock cleanup; git history as audit | [V] `hive.ts` | State | high | rejected as event store (bloat, lock contention; code already untracks files); kept "one writer" idea |
| 3 | Atomic temp-and-rename delivery into the recipient's inbox | [V] | Infrastructure | high | adopted (already `config.write_atomic` in this repo) |
| 4 | Hop cap 12: over-cap messages dropped and logged; docs claim escalation | [V] code vs [D] `HIVE.md` | Automation loop guard | high | adapted: depth cap that **escalates** |
| 5 | Supervisor ("god") policy lives in a long system prompt | [V] | Policy | high | rejected (untestable); Archeus policy is data + code |
| 6 | Hook-return control: PreToolUse deny for paused agents/gated tools, `additionalContext` steering, `continue:false` halt | [V] `src/main/control.ts`, `hooks.ts` | Policy, Execution | high | adopted (policy hook, cooperative pause) |
| 7 | Forced continuation at Stop removed ("bypassed HITL safety and could spend credits") | [V] `hooks.ts` comment | Execution | high | adopted as a rule: never force continuation |
| 8 | Circuit breaker healthy → steering → constrained → stopped, one level per beat, de-escalates on health | [V] `src/main/breaker.ts` | Resource health | high | adapted (account health machine) |
| 9 | Memory condensed with backup → verify → atomic swap; original untouched on failure | [V] `src/main/reflect.ts` | Knowledge | high | adopted |
| 10 | Four-part dispatch contract (objective / output / tools / boundaries) | [V] god prompt | Planning | medium | adopted (Task contract) |
| 11 | Visual office floor as the primary UI | [V] | UI | high | rejected (agents are not the user's abstraction) |

## R2 — Vicoa

| Field | Value |
|---|---|
| URL | https://github.com/vicoa-ai/vicoa |
| Revision | `8933edbe05b864d0eaa555f8bce4146cb96fb69d` (2026-09-23) |
| Inspected | 2026-09-23 |
| License | **AGPL-3.0** — design ideas only; no code reuse |
| Stack | FastAPI, SQLAlchemy/Alembic, Postgres, Next.js web, Electron desktop, Flutter mobile |

| # | Observation | Evidence | Area | Confidence | Status |
|---|---|---|---|---|---|
| 1 | Self-host topology: web, backend (users), server (agents: REST/MCP/WebSocket), Postgres; server must be one replica (in-memory connection manager) | [V] `SELF_HOSTING.md` | Infrastructure | high | validates single-Core design |
| 2 | Machine daemon per computer; heartbeat 30 s; stable hardware fingerprint; re-register on API-key change | [V] `backend/src/vicoa/machine_daemon.py`, `machine_identity.py` | Execution nodes | high | adapted (remote node contract, deferred) |
| 3 | Hello-frame scoped rooms; point-to-point RPC with correlation id, timeout, reconnect grace | [V] `shared/websocket/protocol.py`, `rpc.py` | Realtime | high | adapted (SSE command stream for nodes) |
| 4 | Postgres LISTEN/NOTIFY: must-deliver events wake readers who re-query from a cursor; signals coalesced | [V] `shared/pg_listener.py` | Event system | high | adopted (wake-and-requery over SSE) |
| 5 | Socket-as-liveness with batched lease renewal; removed a UI sweep that faked COMPLETED | [V] `servers/presence.py`, head commit | State | high | adopted: Core decides LOST, never self-report |
| 6 | Tokens in `Sec-WebSocket-Protocol`, never query strings; typed agent/user tokens with revocation | [V] `shared/auth/ws.py`, `agent_tokens.py` | Security | high | adopted (typed hashed tokens, no query-string tokens) |
| 7 | Worktrees under `~/vicoa/workspaces/…` outside the repo; removal only for managed paths | [V] `vicoa/rpc/worktree_ops.py` | Execution | high | adopted |
| 8 | ACP / Codex app-server / Claude SDK permission callbacks vs legacy regex terminal scraping | [V] `integrations/headless/*`, `cli_wrappers/*` | Execution | high | adopted structured protocols; rejected scraping |
| 9 | Scheduler claims due rows with `FOR UPDATE SKIP LOCKED`, advances `next_run_at` in the claim transaction; `AutomationRun` table | [V] `servers/scheduler/loop.py` | Automation | high | adopted (claim-and-advance on the single writer) |
| 10 | Expo push, FCM, Twilio notifications | [V] `servers/shared/notifications.py` | Notifications | high | rejected for V1 (hosted accounts); ntfy instead |

## R3 — Graphify

| Field | Value |
|---|---|
| URL | https://github.com/Graphify-Labs/graphify |
| Revision | `a5957aa6ef51c9be8d054de9783d25046c187f3f` (2026-09-22, branch `v8`, release 0.9.66) |
| Inspected | 2026-09-23 |
| License | Apache-2.0 (GitHub API; a `LICENSE-MIT` file also exists, not opened) |
| Stack | Python, NetworkX, tree-sitter, Leiden clustering, MCP |

| # | Observation | Evidence | Area | Confidence | Status |
|---|---|---|---|---|---|
| 1 | Pipeline detect → extract → build → cluster → analyze → report → export; architecture doc guarded by a test importing every named symbol | [V] `ARCHITECTURE.md`; test [D] | Repository understanding | high | adopted pattern (docs guarded by tests) |
| 2 | Code never sent to the LLM: AST pass; LLM only for docs/PDF/images | [D] `docs/how-it-works.md` | Repository understanding | medium | adopted (deterministic first) |
| 3 | Edge confidence EXTRACTED / INFERRED / AMBIGUOUS; ambiguous listed for human review | [V]/[D] | Knowledge | high | adopted |
| 4 | Two caches: AST cache versioned by extractor; semantic cache by content hash only | [V] `cache.py` | Knowledge | high | adopted |
| 5 | Incremental updates; manifest written only on success; watcher with pending queue + rebuild lock; git hooks | [V] `watch.py`, `hooks.py`; [D] design doc | Repository understanding | high | adopted |
| 6 | MCP query tools; subgraph rendered under a token budget | [V] `serve.py` | Context | high | adopted (token-budgeted packages) |
| 7 | Blast-radius traversal | [V] `affected.py` | Context | high | adopted for drift/impact |
| 8 | Lessons from feedback decay with half-life; "preferred" only after several independent useful results | [V] `reflect.py` | Knowledge | high | adopted (corroboration-gated lessons) |
| 9 | One big JSON graph in memory | [V] | State | high | rejected for a persistent multi-project store |

## R4 — Cognee

| Field | Value |
|---|---|
| URL | https://github.com/topoteretes/cognee |
| Revision | `663a2dc15d04bc0d7ec2733a2dd604b7ed1b8c8e` (2026-09-19, v1.6.0 README) |
| Inspected | 2026-09-23 |
| License | Apache-2.0 |
| Stack | Python async, pydantic, SQLAlchemy, pluggable graph/vector adapters, MCP |

| # | Observation | Evidence | Area | Confidence | Status |
|---|---|---|---|---|---|
| 1 | `remember` without session → permanent (add + cognify); with session → session cache bridged by a debounced background `improve()` | [V] `api/v1/remember/remember.py`, `auto_improve_debounce.py` | Knowledge | high | adapted (execution → mission → permanent memory) |
| 2 | `improve()` stages skip with zero LLM calls when they cannot run; watermarks per session; lock loser requests a rerun | [V] `api/v1/improve/improve.py` | Knowledge | high | adopted for maintenance passes |
| 3 | Feedback weights as EMA with applied-id bookkeeping (idempotent) | [V] `tasks/memify/apply_feedback_weights.py` | Learning | high | deferred past V1 slice (columns exist) |
| 4 | One `forget` entry point incl. `memory_only`; dataset lock | [V] `api/v1/forget/forget.py` | Knowledge | high | adopted (dry-run default) |
| 5 | Cleanup by `last_accessed`, dry-run default, document-level | [V] `tasks/cleanup/cleanup_unused_data.py` | Knowledge | high | adapted (item-level decay) |
| 6 | Contradictions added as edges, never overwriting | [V] `tasks/graph/detect_contradictions.py` | Knowledge | high | adopted (deferred past slice) |
| 7 | 20 search types; rule-based query router with no LLM | [V] `SearchType.py`, `query_router.py` | Context | high | router adopted; 20 types rejected (3 modes) |
| 8 | Runtime-registered graph/vector adapters with embedded defaults | [V] | Infrastructure | high | idea kept behind `infra/search`; not adopted in V1 |

## R5 — Anthropic redesign / migration methodology

| Field | Value |
|---|---|
| Supplied URL | https://x.com/dani_avila7/status/2102212844238275030 |
| Access | direct fetch returned HTTP 402; read through the fxtwitter mirror API [S] |
| Post | Daniel San, 2026-09-22: shares "Anthropic's repository for code migrations with Claude Code"; AI makes migrations "simpler, not easy"; the kit gives structure through rules, dependency mapping, behaviour verification and configuration constraints [S] |
| Linked repository | https://github.com/anthropics/code-migration-kit-with-claude-code @ `cf91c9d5068d9aaf95a36164169f08c3e636c909` (2026-07-08), inspected directly [V]; license field NOASSERTION; marked "reference code, not actively maintained" |
| Companion article | *How Anthropic runs large-scale code migrations with Claude Code* — referenced by the README, not fetched |

| # | Observation | Evidence | Area | Status |
|---|---|---|---|---|
| 1 | Six steps: map + rules, stress-test rules, translate, compile, run, match behaviour | [V] README | Process | adapted to phases |
| 2 | Feasibility report first; "don't migrate" is valid; three committed calls with file evidence | [V] `prompts/00-feasibility.md` | Process | adopted (P0 gate) |
| 3 | "No judge, no exit condition": a parity judge through the public surface, validated against deliberately broken code | [V] README, 00b | Testing | adopted (judge in P1, mutation-verified) |
| 4 | **Redesigning:** rulebook becomes a design document; bakeoff invalid → adversarial review of the design + disposable full runs; unit of work = module/subsystem; behaviour matching still works | [V] README "If you're redesigning" | Process | adopted (these docs; red-team; walking skeleton; subsystem phases) |
| 5 | Fix the process, not the code; a failure seen three times is a rule bug | [V] README, skill | Process, Task machine | adopted |
| 6 | Sign-off gates; queues defined by what exists on disk; stopping is free | [V] README | Process | adopted |
| 7 | Model tier by blast radius; explicit model per subagent | [V] feasibility prompt | Routing | adopted (tier fit) |
| 8 | Guardrail settings installed by the human, never self-installed; deviations logged | [V] `prompts/03-stress-test.md` | Policy | adopted (policy changes only by user devices) |
| 9 | Cost as bands, precise predictions forbidden | [V] feasibility prompt | Planning | adopted |

**Second reference cited by the source documents:** https://x.com/claudedevs/status/2097369738968195513
(2026-09-08) → article "Reducing cost and improving performance with Claude Platform", read via
the same mirror [S]: maximise prompt-cache hit rate (monitor, defer rarely used tools, pre-warm),
remove prompt anti-patterns (verification rituals, emphasis boosters, mandatory procedures) when
upgrading models, calibrate effort per task ("a stronger model at low effort can be cheaper than
a weaker model working hard"). Status: adapted into router economics
([../architecture/resource-router.md §6](../architecture/resource-router.md)).

## R6 — Apple Design Skill

| Field | Value |
|---|---|
| URL | https://github.com/dickwu/apple-design-skill |
| Inspected | 2026-09-23; installed by cloning into the user's Claude skills directory (outside this repository) |
| Contents | `SKILL.md` (review framework), `references/hig-lookup.md`, `references/cross-platform.md`, 124 generated HIG pages |

| # | Observation | Evidence | Area | Status |
|---|---|---|---|---|
| 1 | Five lenses: accessibility, platform conventions, visual design & craft, interaction, content; severity Critical/High/Medium/Low; What/Why/Fix findings | [V] `SKILL.md` | Design review | adopted |
| 2 | Numbers: contrast 4.5:1 / 3:1; targets 44/28 pt mobile, 28/20 pt desktop; type 17/11 pt mobile, 13/10 pt desktop; sidebars ≤ 2 levels | [V] | Design system floors | adopted |
| 3 | Template detection: three dominant generated looks, incl. near-black + acid accent | [V] | Visual language | adopted as a check |
| 4 | Improvement mode: tokens before layout; one signature element; "would this plan fit another product?" | [V] | Design process | adopted |
| 5 | HIG *Generative AI* (2026-06-08): keep people in control, refine/revert, ask before irreversible actions, specific progress text, disclosure, voluntary feedback | [V] `references/hig/generative-ai.md` | Conversation UX | adopted |
| 6 | Cross-platform translation (tab bar ↔ bottom navigation; size classes ↔ container queries; menu bar/tray commands) | [V] `references/cross-platform.md` | Platform adaptation | adopted |
