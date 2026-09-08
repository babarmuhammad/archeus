---
description: >-
  archeus's task-scoped, token-budgeted project memory — a semantic graph of your codebase
  injected through three surfaces, bounded as the project grows, and learning durable
  lessons from every session.
---

# Project memory

The feature that makes archeus unique: **task-scoped, token-budgeted memory injection at
the launcher**. Claude remembers the whole project while paying the fewest possible tokens
— three injection surfaces, zero duplication.

Reached with `m` in the sessions menu (the memory hub), or the **Memory** project tab in
the GUI.

## The three surfaces

| Surface | What Claude sees | Cost |
|---|---|---|
| CLAUDE.md micro-index | repo one-liners + module names + recall pointer | ≤250 tok, every session |
| `.claude/rules/archeus-mem-*.md` | per-module entities & relations, `globs:`-scoped | **0 until Claude touches those files** |
| `UserPromptSubmit` hook (opt-in) | the subgraph relevant to *your current prompt*, budget-cut | ≤600 tok/prompt, <1s local |

## How it works

- **Whole-project extraction** — `claude.exe` summarizes every repo and module (incrementally by file hash), merged with the **real dependency graph** (cross-module edges + importance rank) from the [connections engine](architecture.md). Stored in `.archeus/memory/graph.json`.
- **Bounded & self-consolidating** — the graph stays lean *as the project grows*: duplicate entities merge across modules, and a global importance cap (`memory_max_entities`, default 500) evicts the least-connected. So the always-on token cost stays flat while accuracy rises — the memory gets *leaner and sharper* the more you build, not heavier.
- **Nothing shrinks without a way back.** Every operation that can *reduce* memory is fenced, pinnable, previewed and reversible:
    - **Pin** any entity or lesson and the importance cap can never evict it — if you pin more than the cap allows, the pins win and the cap gives way.
    - **Fence** a section of CLAUDE.md between `<!-- ARCHEUS:KEEP:START -->` and `<!-- ARCHEUS:KEEP:END -->` (audit screen → *Protect a section*) and AI compression never even *sends* it to the model, so it cannot be reworded, shortened or dropped.
    - **Preview** — prune names the exact session entries it will drop before it drops them, and asks; compression shows the full diff.
    - **Undo** — every replacement is snapshotted (12 versions of CLAUDE.md and of the graph), browsable with a diff and restorable from the audit screen's *History* panel. Restoring is itself snapshotted, so you can walk back out again.
- **Temporal facts (Graphiti-style)** — when the code changes and a fact is superseded (you migrated Flask→FastAPI), the old fact is **invalidated with a timestamp, not deleted** — kept as history, never injected. Memory tracks *what's true now* and *what changed*, instead of drifting stale.
- **Reinforcement + rollups** — entities recalled often gain weight and survive consolidation; dead knowledge fades (access-based, like a forgetting curve). Per-repo **rollup summaries** (GraphRAG-style, built locally — no extra Claude call) give an accurate one-line repo overview and cheap global answers. Plus Obsidian-style **unlinked-mention** edges enrich retrieval for free.
- **Recall engine** — four local rankers (BM25 over names and summaries, path/module match, dependency rank, and a confidence-weighted lesson signal) combined by **Reciprocal Rank Fusion**, which uses each ranker's *position* rather than its score, so nothing needs calibrating. No embeddings, deterministic, <0.5s on 500 entities. On-demand CLI: `archeus recall "<topic>"` — Claude itself can call it mid-session via Bash.
    - A stopword floor means a contentless prompt retrieves **nothing**; the earlier IDF could never reach zero, so the query `the` alone returned 33 entities on this repo's own graph and the prompt hook injected memory into prompts that asked for none.
    - The budget **fits** rather than truncating: one verbose top hit no longer discards every smaller fact behind it.
    - Reinforcement credits what was actually injected, not everything that ranked, and it is folded in even when nothing needed re-extracting — on this repo the sidecar had recorded 807 hits while the highest counter in the graph was 1.
    - **The honest limit:** this is lexical retrieval. A query that shares no vocabulary with the stored summary will miss, and no weight tuning changes that. `tests/test_recall_eval.py` measures recall per category so a regression names the signal that broke.
- **Session learning** — after each session archeus distills durable *lessons* (error→fix pairs, decisions, preferences) from the transcript. High-confidence lessons **auto-approve** (`memory_lessons_autoapprove`); the rest wait in the `⇧L` review screen. Approved lessons boost recall and decay if unused. The project literally gets smarter the more you use it.
- **Cross-project conventions** — preferences, corrections and decisions that recur across your repos (or you pin) are promoted to a small block in your user-level `~/.claude/CLAUDE.md`, so a convention learned once ("this machine uses PowerShell 5.1", "prefer pytest") is remembered in *every* project. Scanned across **every account** and both graph locations. A reviewed rule needs two projects; an unreviewed one needs three, because recurrence at that scale is its own evidence. When nothing qualifies the card lists the **near-misses** with a Pin button, so it tells you how to fill it rather than only that it is empty. No competitor spans projects.
- **Auto-refresh that actually converges.** Turn it on per project (memory hub → `o`, or the checkbox on the GUI's memory tab — one flag, honoured by both interfaces and by the background worker) and **memory does not go stale while it is on**:
    - Each cycle extracts at most `auto_cap` modules and leaves the rest queued; the scheduler then comes back in seconds rather than waiting the full interval, so a busy repo catches up instead of stalling. It used to do *nothing at all* once more than six modules had changed — the harder you worked, the less it updated.
    - It **bootstraps**: a project with no graph yet is built by the same budgeted cycles. The first build no longer has to be manual.
    - Work is never marked done unless it was done. A failed extraction keeps the facts it could not replace and re-queues the module; a capped run leaves the modules it skipped genuinely stale. Both used to record their file hashes as current, so the skipped work became invisible forever and a failed call *wiped* that module's memory.
    - A cycle that finds nothing to do still re-verifies freshness, so a commit touching no source file can't leave the workspace screen reporting stale memory.
- **Staleness costs almost nothing to check.** Files are compared by `(mtime, size)` first and only re-hashed when that moves — an unchanged project is a stat per file, not a full SHA-256 read of every source file on every tick. Content hash stays the source of truth, so `touch` never bills a model call. Install the **stale-on-edit hook** (Hooks → `memory-stale-on-change`) and the files Claude edits are known the instant they change; the periodic scan stays as the reconciler for edits made outside Claude Code.
- The update runs in a **detached background worker** that survives launching a session, saves after every step (an interruption never loses progress), shows live progress in the sessions menu, and reports what it actually did — including **failures**, which previously reached nobody at all.
- **Memory hub** (`m` in the sessions menu) — one screen for everything: status, build, ask, injection preview with live "what would my prompt inject?" probe, lessons, **work suggestions** (`s` — next-steps from lessons, graph rank, health, context freshness with the key that clears it, the repo's own TODO/`ponytail:` markers and untested modules; all local and free, plus an optional one-call *Find work* scan that adds bugs, vulnerabilities, slow paths and functions worth building), **since-last-session diff** (`d` — git + session-log), per-surface toggles.
- **Ask the project** — grounded Q&A over the graph, answered by Claude with only the relevant subgraph as context. Asking is a query, not memory being built, so it is not counted against the lifetime spend below.
- **You can see all of it.** Memory is not one file — it is a graph, a digest inside CLAUDE.md, a rule file per module, a worklog, two sidecars, the conventions block, a manifest, lessons, snapshots and the per-prompt injection. The GUI's Memory tab inventories every one of them with what writes it, how far it reaches into a session (**always / lazy / per prompt / never**) and what it costs, so the trade-off is legible: the digest is read on every turn while several KB of path-scoped rules cost nothing until Claude opens a matching file. Alongside it: what the last cycle did and spent, **cumulative spend for the project**, what eviction dropped by name, which facts recall reinforces most, and how many sessions each lesson is from being dropped.
- **A preview never reinforces.** Opening the recall preview shows exactly which entities would be injected and why the text looks the way it does — without logging a hit. Reinforcement credits what Claude actually saw, so inspecting memory cannot reshape it.

*(Graph memory inspired by [cognee](https://github.com/topoteretes/cognee); retrieval
budgeting inspired by [Aider's repo-map](https://aider.chat/docs/repomap.html); both
reimplemented from scratch — pure stdlib.)*

## CLAUDE.md and system prompts

- **Scaffold CLAUDE.md** (`c`) — build project context mechanically from git repos, recent commits, READMEs, and prior session topics
- **AI CLAUDE.md generation** (`a`) — Claude deep-analyzes the codebase and writes/updates a comprehensive CLAUDE.md; reviewed before writing
- **System prompts** (`s`) — AI-generate or hand-edit a per-project system prompt injected on every launch
- **Memory map** (`M`) — see which CLAUDE.md files load for a project (user / project / .claude / local) and their `@import`s; open any in your editor. In the GUI an `@import` pointing at a file that no longer exists is flagged **missing** — Claude loads nothing for it and says nothing.
- **Block by block** — the GUI's CLAUDE.md tab shows the file as what it is made of (your prose, KEEP-fenced regions, AUTOGEN, SESSIONS, MEMORY digest), each with its token cost and the one button that regenerates that block alone. Prune, for instance, only ever touches SESSIONS.

Exactly what each generator reads and which blocks it rewrites is in
[CLAUDE.md auto-generation](reference.md#claudemd-auto-generation).

## Recent-work memory

Opt-in per project (Memory tab / `⇧W` in the hub). Records a token-free one-line summary +
files touched at the end of each session and injects a compact digest on the next
`SessionStart`, so Claude knows what the last few sessions did.

## Keeping it honest

Everything memory generates is tracked for provenance and freshness — see
[Workspace status](projects.md#workspace-status). Where the token budget goes, and how to
cut it further, is on the [Token economy](usage.md) page.
