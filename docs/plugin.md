---
description: >-
  The archeus Claude Code plugin — three slash commands and eight skills inside the
  session itself, how to install it, and why it deliberately ships no hooks.
---

# Claude Code plugin

The in-session surface. archeus ships as a Claude Code plugin, which puts its three most
useful commands and its eight skills inside the conversation rather than in a separate
window.

```
/plugin marketplace add babarmuhammad/archeus
/plugin install archeus@archeus
```

## What it adds

| | |
|---|---|
| `/archeus:recall <topic>` | This project's task-relevant memory, scored locally against the topic — no model call |
| `/archeus:status` | Memory age, repositories and worktrees, health checks |
| `/archeus:review` | Review the current diff against this project's own learned conventions |
| 8 skills | changelog, code-explainer, commit-message, pr-description, refactor-planner, security-review, test-writer, token-economy |

The three commands shell out to the `archeus` CLI, so [install that](installation.md)
too:

```
pipx install archeus     # or: pip install archeus
```

The skills work on their own, without the CLI.

## Skills, and where they come from

The bundled skills live in the package at `claude_sessions/skills_templates/<name>/SKILL.md`
and are generated into the plugin's own root, because `package-data` cannot reach outside
the package and the plugin needs them at its root. They are the same starters the
[skills manager](agents.md#skills) offers, so installing the plugin and copying them from
the manager gives you the same files either way.

A skill loads **on demand** — Claude reads `SKILL.md` when the task matches, not on every
turn — which is why they are skills rather than more `CLAUDE.md`. See
[Usage & cost](usage.md).

## What it deliberately does not add

**Hooks.** archeus already installs its own — the memory-recall hook, the worklog
capture, the guard hooks — through a [manager](hooks.md) that places them per account and
can show, repair and remove them.

Shipping the same hooks in the plugin would give two owners to one entry in
`settings.json`: installing both runs the recall hook twice on every prompt, and
uninstalling either leaves the other behind looking broken. `${CLAUDE_PLUGIN_ROOT}` exists
and hooks *can* be inlined in `plugin.json` — the constraint here is ownership, not
capability.

Use `archeus` → Hooks.

## Updating and removing

The plugin is versioned with archeus itself and updates through Claude Code's own
`/plugin` commands. It is independent of the CLI install: removing one leaves the other
working.

The plugin marketplace and install caches are Claude Code state whose format has already
changed once, so archeus never rewrites them directly — every plugin mutation it makes
shells out to the `claude` CLI.
