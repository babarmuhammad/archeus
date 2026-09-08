---
description: >-
  Every file archeus reads and writes — per-project files under ~/.claude/projects and in
  the working directory, the global CLAUDE.md, its own settings file, and the repository
  layout.
---

# Configuration

Where everything archeus uses lives on disk. Nothing here is a database and nothing is
uploaded anywhere: every file below is plain text or JSON you can read, edit and delete.

## Where the settings are, in the app

In the desktop app **Settings** is five sub-tabs rather than one long page — the same five
in the terminal UI's `⚙ Settings` submenu and in this section of the documentation:

| Sub-tab | What it holds |
|---|---|
| **Launch** | What every new session starts with: effort, model, permission mode, thinking cap, subagent model, the window it opens in — and the plan/execute model pair |
| **Appearance** | Palette, skin, world, motion, surface transparency, background brightness and which background scene runs |
| **Paths & limits** | Editor and `claude.exe` paths, `CLAUDE_CONFIG_DIR`, the per-call budget cap, the memory-graph ceilings, the economy model, the statusline and the OpenTelemetry export |
| **Models** | Free execution through [OmniRoute](plan-execute.md) and the failover list |
| **Updates** | Update checks, desktop notifications and the auto-memory schedule |

Each card keeps its own **Save**: one button covering a page of unrelated settings is a
button you cannot press with confidence. Appearance is the exception — a palette is a
setting you judge by looking at it, so it applies and saves the moment you click a card.

## Its own settings

archeus's settings live at `~/.claude/archeus.json` — accounts, defaults, theme, editor
path, `claude.exe` path, economy model. It is **always read from `~/.claude`**, independent
of the config dir you are using, so switching account does not switch your preferences.

Safe to edit by hand or delete to reset. Settings written by a newer archeus are
preserved by an older one: the reader carries keys it does not recognise, so syncing the
file between two machines with different versions cannot erase either one's configuration.

Two more files sit beside it, both account-independent for the same reason:

| File | Purpose |
|------|---------|
| `~/.claude/archeus-events.jsonl` | archeus's own event log — what it did and what failed. Capped at 256 KB. See [Logs](tui.md#logs) |
| `~/.claude/failover.log` | the local failover proxy's request log, when it is running |

`headless_quota` (`prompt` / `auto` / `off`) decides what happens when archeus wants to
make one of its own Claude calls and the account's limit is already full — see
[Rate limits and a second account](tui.md#rate-limits-and-a-second-account).

## Per-project files

Each project gets a folder at `~/.claude/projects/<encoded-name>/`. archeus reads and
writes several files there:

| File | Purpose |
|------|---------|
| `<session-id>.jsonl` | Claude Code session transcript (managed by Claude Code) |
| `<session-id>.name` | Custom display name you set with r |
| `extra-paths.txt` | Additional PATH directories added when launching Claude |
| `add-dirs.txt` | Directories passed via `--add-dir` on every launch |
| `system-prompt.txt` | System prompt injected via `--system-prompt-file` on every launch |
| `tags.json` | Per-session tags (`sid → [tags]`) |
| `session-agents.json` | Selected agent refs, keyed by `__project__` (project-level picks) |
| `archived/` | Archived sessions (restorable from the A view) |

In the project's **working directory** (not the encoded folder), archeus also maintains:

| File | Purpose |
|------|---------|
| `.claude/agents/*.md` | Selected library agents, copied here so Claude auto-discovers them |
| `.claude/agents/.archeus-managed.json` | Filenames archeus placed (so it never removes your own agents) |
| `.archeus/workspace-manifest.json` | Provenance & freshness manifest (repo HEAD, hashes, sessions, MCP, timestamps) |
| `.archeus/memory/graph.json` | Claude-extracted semantic memory (entities, relations, per-repo/module summaries) |
| `.archeus/connections-cache.json` | Cached architecture graph (rebuilt when the file signature changes) |
| `.archeus/connections-graph.html` | The rendered interactive architecture graph (opened in the browser) |
| `.archeus/snapshots/` | Previous versions of generated files (for the `w` change diffs) |

The agent library lives at `~/.claude/archeus-agents/<category>/*.md` (account-wide, not
auto-loaded); selecting agents for a project copies them into that project's
`.claude/agents/`. A single lead agent can also come from `~/.claude/agents/`. Hooks and MCP
servers are stored in `settings.json` / managed via `claude mcp`.

!!! note "`settings.json` is Claude Code's file, not archeus's"

    Hooks, permissions and the output style all live in Claude Code's own
    `settings.json`. archeus read-modify-writes it — never rewrites it — and every write
    goes through one atomic helper, because a half-written `settings.json` breaks the
    user's entire session and not just archeus.

## Global CLAUDE.md

`~/.claude/CLAUDE.md` is loaded by Claude Code in every session across all projects.
archeus uses it to store MCP tool documentation. Each MCP server gets its own
sentinel-delimited section:

```
<!-- MCP:Notion:START -->
## MCP: Notion
… tool listing …
<!-- MCP:Notion:END -->
```

Re-running the analysis for the same server updates only that section; other content is
untouched. Access via: main screen → **⚙ Global CLAUDE.md / MCP Analysis**, or the Global
CLAUDE.md page in the [desktop app](desktop.md).

Because it loads in **every** project, its size is a per-turn tax everywhere; the
[context weight audit](usage.md#context-weight-audit-w) counts it separately from the
per-project file for exactly that reason.

## File layout

```
.\archeus\
├── claude-sessions.py      # launcher stub: applies theme, --launch, crash handler
├── Open Repo cmd.bat       # bat launcher (runs TUI, then py --launch)
├── pyproject.toml
├── README.md
├── tools\                  # dev utilities: GUI smoke/screenshot audits, graph renders, icons
├── tests\                  # pytest suite (Windows-only, no network, no real claude.exe)
└── claude_sessions\        # package
    │
    │  # entry points
    ├── main.py             # run() — subcommand dispatch, project discovery, launch flow
    ├── cli.py              # console-script target; dispatches statusline before importing main
    ├── __main__.py         # `python -m claude_sessions`; same early statusline dispatch
    │
    │  # core
    ├── config.py           # constants, paths, settings, write_atomic, theme application
    ├── paths.py            # encode_component, find_actual_path, resolve_dir
    ├── sessions.py         # session parsing + persistence helpers
    ├── render.py           # frame-diff renderer, layout + hint helpers
    ├── themes.py           # PALETTES / SKINS / WORLDS — single source of truth for colour
    │
    │  # TUI screens
    ├── ui.py               # menu, pager, multiselect, confirm, launch options, settings
    ├── session_menu.py     # per-project sessions menu
    ├── search.py           # cross-project session search
    ├── transcript.py       # transcript viewer + markdown export
    ├── stats.py            # usage stats dashboard
    ├── usage.py            # plan usage limit bars (OAuth poll)
    ├── brief.py            # "since last session" digest
    ├── checkpoints.py      # read-only view of Claude Code's file-history store
    │
    │  # Claude Code integration
    ├── mcp.py              # MCP manager + background status poll
    ├── agents.py           # agent library, per-project selection, scaffold/AI
    ├── skills.py           # skills manager + bundled starter templates
    ├── skillscan.py        # static risk scan of a skill before installing it
    ├── hooks.py            # hooks template / toggle / remove
    ├── plugins.py          # plugin marketplaces + installs (shells out to `claude`)
    ├── outputstyles.py     # output-style browse / save / select
    ├── statusline.py       # `archeus statusline` — renders the Claude Code status line
    ├── accounts.py         # multiple CLAUDE_CONFIG_DIR accounts
    ├── denygen.py          # generated permissions.deny rules for heavy paths
    ├── health.py           # project health checks + auto-fixes
    ├── quota.py            # don't spend an exhausted account — offer one with headroom
    ├── events.py           # archeus's own event log + the Logs screen
    ├── *_hook.py           # the hook scripts themselves (guard, recall, worklog, …)
    │
    │  # memory & context
    ├── memory.py           # Claude-powered semantic memory (ECL + ask)
    ├── memhub.py           # cross-project memory index
    ├── memrules.py         # per-module .claude/rules generation
    ├── lessons.py          # durable lessons distilled from transcripts
    ├── recall.py           # `archeus recall "<topic>"` — task-relevant subgraph
    ├── worklog.py          # recent-work ring buffer per project
    ├── conventions.py      # inferred repo conventions
    ├── context_inject.py   # cross-session context hand-off
    ├── ctxaudit.py         # context weight audit
    ├── claude_md.py        # scaffold + AI CLAUDE.md, autogen/sessions blocks
    ├── system_prompt.py    # edit / AI-generate the per-project system prompt
    │
    │  # git & repos
    ├── repos.py            # repo discovery, cached state, _git (the one git door)
    ├── worktrees.py        # linked-worktree board
    ├── workspace.py        # provenance manifest + freshness status
    ├── review.py           # `archeus review` — diff review
    ├── diffview.py         # git-style diffs + the approval gate for generated files
    ├── connections.py      # project architecture graph (standalone HTML)
    │
    │  # model routing
    ├── plan_execute.py     # Plan→Execute: plan with one model, execute with another
    ├── omniroute.py        # OmniRoute free-tier client (model catalog, health)
    ├── failover.py         # local proxy: retry a dead model instead of hanging
    │
    │  # GUI
    ├── gui.py              # loopback HTTP server, _guard(), launch endpoint
    ├── gui_api.py          # GUI job layer — TUI flows headless + diff-approval gates
    ├── gui_html.py         # page assembly + the /vendor/ allowlist
    ├── gui_qt.py           # optional PyQt6 native window shell
    ├── web\                # the SPA: app.js, app.css, stage.js, motion.js, instruments.js
    └── skills_templates\   # bundled starter SKILL.md files
```

The HTTP routes the desktop app is built on are catalogued in the
[API reference](api.md), generated from the route tables themselves.

## See also

- [Projects](projects.md#workspace-status) — the provenance manifest and what makes a
  component stale
- [Files, layout & encoding](reference.md) — how Claude Code encodes project paths into
  folder names, and how `CLAUDE.md` is generated
- [Usage & cost](usage.md) — what each of these files costs per turn
