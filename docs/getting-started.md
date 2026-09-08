---
description: >-
  The memory and workspace layer for AI coding agents. What archeus is, the three surfaces
  it offers — terminal UI, desktop app and Claude Code plugin — and which page of the
  manual to read next.
---

# Getting started

**The memory and workspace layer for AI coding agents.** archeus sits in front of the
agent rather than replacing it, and does not proxy your conversations: it configures the
agent, launches it with the model, effort, permissions and context you meant, and
maintains the project's context between sessions. Claude Code is the agent it drives
today.

Concretely, that is four jobs:

| | |
|---|---|
| **Memory** | A semantic graph of the codebase, injected through three token-budgeted surfaces so a fresh session starts already knowing the project. |
| **Workspace** | Every folder the agent has ever opened, every session inside it — browsable, searchable, taggable, forkable, archivable, across every account. |
| **Launch control** | Model, reasoning effort, permission mode, subagents, worktree, account — chosen per project and remembered. |
| **Cost** | What a turn costs across every surface at once, and the tools to cut it. |

It is pure Python standard library with zero runtime dependencies, and it uses the Claude
Code authentication you already have. No API key.

!!! note "Where this is going"

    A long-term goal, not a feature, and none of it ships today: provider-neutral memory,
    then an open harness of its own. Claude Code is the first surface, not the boundary.
    Everything documented on this site works against the files Claude Code writes to disk,
    and nothing else is supported yet.

## The three surfaces

The same engine, three ways in. Pick whichever you prefer — they do the same things.

<div class="grid cards" markdown>

- **[Terminal UI](tui.md)** — `archeus`

    Keyboard-first, one screen per job, instant. The default. Every action has a key and
    `?` prints the map.

- **[Desktop app](desktop.md)** — `archeus --gui`

    The whole workspace as a local app on loopback, with the dashboard, the usage banner
    and the theme system. Full parity with the terminal UI.

- **[Claude Code plugin](plugin.md)** — `/plugin install`

    Three slash commands and eight skills *inside* a session, for recall, status and
    review without leaving the conversation.

</div>

The [command line](cli.md) is the fourth way in and the one scripts and hooks use — no UI,
one answer on stdout.

## Where to go next

| | |
|---|---|
| [Installation](installation.md) | pipx, pip, a checkout, the desktop window, Windows shortcuts |
| [Quickstart](quickstart.md) | install to first session in five minutes |
| [Configuration](configuration.md) | every file archeus reads and writes, and where |
| [Projects](projects.md) | health checks, auto-fixes and whether the generated context still matches the repo |
| [Sessions](sessions.md) | browse, search, tag, fork, resume, archive, export |
| [Project memory](memory.md) | the memory graph and its three injection surfaces |
| [Architecture graph](architecture.md) | the interactive dependency view |
| [Usage & cost](usage.md) | what you spend per turn, and how to cut it |
| [Troubleshooting](troubleshooting.md) | when something does not work |

Reference material — the [HTTP API](api.md), [multiple accounts](accounts.md),
[MCP servers](mcp.md), [agents & skills](agents.md), [hooks](hooks.md),
[Plan → Execute](plan-execute.md), the [status line](statusline.md) — is in the Reference
section of the sidebar.
