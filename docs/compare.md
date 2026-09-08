---
title: archeus vs bare Claude Code — alternatives compared
description: >-
  The memory and workspace layer for AI coding agents, compared honestly against bare
  Claude Code, /resume, manual CLAUDE.md maintenance and terminal multiplexers —
  including what archeus does not do.
---

# archeus compared

**The memory and workspace layer for AI coding agents.** Claude Code — the agent archeus
drives today — already works. This page is about what it does *not* do between sessions,
which alternatives cover, and where archeus is the wrong choice.

## At a glance

| | Bare Claude Code | Terminal multiplexer (tmux/Windows Terminal) | Hand-maintained `CLAUDE.md` | archeus |
|---|---|---|---|---|
| Browse past sessions | `/resume`, current directory, recent only | No | No | Every session, every project, every account |
| Search session content | No | No | No | Yes |
| Tag / fork / archive sessions | No | No | No | Yes |
| Project context for the agent | You write it | No | You write and prune it | Maintained automatically, budgeted |
| Context cost as project grows | Grows with your file | — | Grows with your file | Bounded index + on-demand detail |
| See MCP servers per project | Read the JSON | No | No | Listed, with tool analysis |
| Multiple accounts | Set `CLAUDE_CONFIG_DIR` yourself | Per-pane env vars | — | Detected and merged, picked at launch |
| Per-project model / effort / permissions | Flags each launch | Shell aliases | — | Saved per project |
| Dependency graph of the codebase | No | No | No | Interactive graph |
| Extra runtime dependencies | — | The multiplexer | — | None (stdlib only) |

## Versus `/resume`

`/resume` is the closest built-in. It reattaches you to a recent session in the current
directory, and for "put me back where I was five minutes ago" it is faster than anything
else — including archeus.

It is not an archive. It does not search, does not span projects or accounts, does not tag
or fork, and does not decide how the next session should start. If your question is "what
did I do in this repo three weeks ago and what did we decide", `/resume` cannot answer it.

## Versus maintaining `CLAUDE.md` by hand

A hand-written `CLAUDE.md` is the right tool for a small project with stable conventions.
It is precise, you control every word, and there is nothing to learn.

It degrades with size. The file is loaded on every message, so its cost is paid constantly
and grows monotonically as you add to it — and the usual failure is not that it is wrong,
but that it is too big to justify and too tedious to prune. archeus keeps the always-on
block bounded and pushes detail into path-scoped rules that load only when relevant. If
your `CLAUDE.md` is 40 lines and stays that way, you do not need this.

## Versus a terminal multiplexer

tmux, screen or Windows Terminal panes solve *running* several sessions at once. That is a
genuinely different problem, and archeus does not replace them — run archeus inside
one if you like. Multiplexers have no idea what a Claude Code session is, so they cannot
browse, search or contextualise anything.

## What archeus does not do

Stated plainly, because a comparison page that only lists strengths is not useful:

- **It is not a Claude Code replacement.** It configures and launches Claude Code; every
  actual coding turn is Claude Code doing the work.
- **It is Windows-first.** macOS and Linux are supported and tested in CI, but Windows gets
  the widest version matrix and by far the most real-world use.
- **It does not host or proxy a model of its own.** It uses your existing Claude Code
  authentication and your existing quota.
- **The memory features cost tokens to build.** Extraction and lesson distillation are
  Claude calls. They are routed to a cheap model and run rarely, but they are not free —
  the saving is on the per-message context you stop paying for.
- **It drives Claude Code only, today.** Provider-neutral memory and an open harness of
  its own are a long-term goal, not a feature — nothing else is supported yet.
- **It is a young project.** Small user base, and the API surface still moves.

## When to use which

- **Just started, one repo, short sessions** → bare Claude Code. Add a small `CLAUDE.md`
  when you find yourself repeating instructions.
- **One repo, long-lived, lots of conventions** → hand-written `CLAUDE.md` is likely
  enough.
- **Several repos, months of history, more than one account, or a `CLAUDE.md` you have
  stopped wanting to pay for** → archeus.

[Install](installation.md){ .md-button .md-button--primary }
[Features](https://claudectl.space/features/){ .md-button }
