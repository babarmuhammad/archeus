---
description: >-
  How archeus reduces the per-turn context cost of Claude Code — a bounded always-on
  index, path-scoped rules, task-scoped injection, the context weight audit, deny rules and
  economy model routing.
---

# Usage & cost

What you spend per turn, and how to spend less.

`CLAUDE.md` and memory files ride in the model's context on **every** message, so their size
is a permanent per-turn tax. archeus makes that cost visible and cuts it.

Without archeus, a big project either starves the agent (no context) or floods it (a huge
CLAUDE.md loaded every message). archeus spends the *minimum* tokens for the *maximum*
relevant context:

| | |
|---|---|
| **Flat always-on cost** | The CLAUDE.md block is a ≤250-token index, not a full dump; it does **not** grow as the codebase grows (consolidation + rollups keep it bounded). |
| **On-demand detail** | Per-module knowledge lives in path-scoped `.claude/rules/` (loads only when Claude touches those files) and in `archeus recall`, so nothing is paid for until it's relevant. |
| **Task-scoped injection** | The optional prompt hook injects only the subgraph your prompt actually needs (budgeted, default ≤600 tok), instead of everything. |
| **No stale weight** | Superseded facts are invalidated, not carried; dead entities are evicted; only current, useful knowledge is ever sent. |
| **Cheaper model for the grunt work** | [Plan → Execute](plan-execute.md) runs the expensive model once for the plan and a cheap one for execution; the token-burn advisor nudges you off Opus for routine work. |

The mechanics behind the first four rows are on the [Project memory](memory.md) page.

## Measuring and cutting the cost

### Context weight audit (`⇧W`)

One screen estimating the tokens auto-loaded on every turn for this project: CLAUDE.md
broken into its blocks (manual / autogen / session topics / memory digest), the global
`~/.claude/CLAUDE.md`, `.claude/rules/*` (marked *lazy* when glob-scoped, so they cost
nothing until a matching file is touched), `system-prompt.txt`, SessionStart hook
injections, and MCP servers — with a running always-on total and inline warnings (CLAUDE.md
over 200 lines, an unbounded session-topics block, a global CLAUDE.md that loads in every
project).

### Prune the unbounded bits (`p` in the audit)

The CLAUDE.md session-topics log used to grow forever; it's now capped to the most recent N
entries (`claude_md_sessions_cap`, default 10) and the autogen commit list is configurable
(`claude_md_commits`). Prune rebuilds them in place without touching your manual prose or
the memory block.

### Compress CLAUDE.md with AI (`⇧C`)

Rewrites the hand-written part into a lean lookup-table style (targets under 500 tokens),
shows a before→after token count and a git-style diff to approve, keeps a `CLAUDE.md.bak`,
and preserves the machine-maintained blocks verbatim.

### Launch economy controls

The launch-options screen adds a **Think cap** (`MAX_THINKING_TOKENS`) and **Subagents**
model (`CLAUDE_CODE_SUBAGENT_MODEL`) field, plus an **`e` economy preset** (Sonnet · 8k
thinking cap · Haiku subagents) in one key. Set defaults in Settings or per project.

### Deny heavy reads (`d` in the audit)

Scans the project and writes `permissions.deny` rules (`node_modules/**`, `dist/**`,
lockfiles, …) into the project's `.claude/settings.json` so a stray read can't pull thousands
of tokens of generated content into context. Merges without clobbering existing settings.

### Token-saver hooks

`concise-output` (a SessionStart rule: no narration, no re-printed code) and
`filter-test-output` (rewrites `pytest`/`npm test`/`go test` commands to pipe through a
failures-only filter before the output hits context) join the [hooks manager](hooks.md)
alongside the existing code-minimization hook.

### Compact instructions

Scaffolded/AI-generated CLAUDE.md includes a `# Compact instructions` section that steers
Claude Code's auto-compaction toward what matters; the audit offers to add one (`i`) if it's
missing.

## Economy model routing

archeus's own internal Claude calls (memory extraction, lessons, CLAUDE.md / agent / hook
/ skill generation) default to **Haiku** to cut cost, while your actual coding sessions keep
whatever model you choose. Change it in **⚙ Settings → Economy model** (`extract_model`).

For free execution rather than cheap, see
[Plan → Execute & OmniRoute](plan-execute.md).

## Related workflow features

- **Skills** — `.claude/skills/<name>/SKILL.md` files load on demand instead of bloating `CLAUDE.md`. See [Agents & skills](agents.md#skills).
- **Code review** — `archeus review [--staged] [--branch <base>]` reviews your working diff against your `CLAUDE.md` rules + learned memory lessons and reports **confidence-scored** findings (only ≥80% shown). Also on the project **Review** tab (GUI) and the `⇧R` key in the session menu.
- **Recent-work memory** — a token-free one-line summary per session, injected as a compact digest on the next `SessionStart`. See [Project memory](memory.md#recent-work-memory).
