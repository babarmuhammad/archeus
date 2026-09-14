---
description: >-
  Every archeus command — the UI launchers, workspace status, recall, review,
  sync-accounts, the status line renderer and the failover proxy — and the flags each takes.
---

# Command line

archeus is a UI, but every job it does headlessly has a command, and those are what
scripts, hooks and the status line call. None of them opens a window.

| Command | What it does |
|---------|--------------|
| `archeus` | Open the workspace UI — the [terminal UI](tui.md), or the [desktop app](desktop.md) if `ui_mode` is set to `gui` |
| `archeus --gui` / `--tui` | Force one interface for this run, ignoring the setting |
| `archeus --help` | Every command, what the tool does, and where its state lives |
| `archeus --version` | The installed archeus version |
| `archeus workspace status` | Freshness report for the repo in the current directory |
| `archeus recall "<topic>"` | Print the task-relevant subgraph of this project's memory |
| `archeus review [--staged\|--branch BASE]` | Review the working diff, staged diff, or the whole branch |
| `archeus sync-accounts [--yes\|--dry-run]` | Level every account up to what you have provisioned |
| `archeus statusline` | Render one status line from the JSON payload on stdin |
| `archeus --failover-serve [port]` | Run the model-failover proxy in the foreground |
| `archeus --failover-stop` | Terminate the failover daemon named in the lock file |

`python -m claude_sessions <same args>` works identically, and is what the installed status
line and the background memory worker use — it needs no console script on PATH.

`--help` and `--version` are answered by a module that imports the standard library only:
they are the first thing a new install types, so they must neither pay for the UI stack nor
be breakable by anything in it.

## `workspace status`

Prints the [provenance and freshness](projects.md#workspace-status) of the context
archeus generated for the repo in the current directory — whether it still matches the
code it was generated from.

```
$ archeus workspace status
  Workspace Status
  ────────────────
  Repo HEAD         5f39fcb  (main)
  Sessions analyzed 20
  MCP servers       3
  CLAUDE.md status  🟢 Fresh
  MCP docs status   🟢 Fresh
  Repo changed      No
  Safe to launch    Yes

  Workspace freshness score: 96%  ▕███████████████████░▏
```

No UI and no Claude call, so it is safe from a script or a hook. Viewing status is
read-only — it never rewrites the manifest.

## `recall "<topic>"`

Prints the slice of this project's [memory graph](memory.md) relevant to the topic, scored
locally with no model call. This is exactly what the recall hook injects into a session and
what the generated `CLAUDE.md` points Claude at, which is why it is a command: Claude can
run it itself, on demand, instead of being handed everything up front.

## `review`

Reviews the working tree against this project's own `CLAUDE.md` rules and learned memory
lessons, and prints confidence-scored findings to stdout (only ≥80% shown).

```
archeus review                      # the working diff
archeus review --staged             # staged changes only
archeus review --branch main        # the whole branch against a base
archeus review --min-confidence 90 [PATH]
```

Also available as `⇧R` in the sessions menu and on the desktop app's Review tab.

## `sync-accounts`

Levels every configured account up to what you have provisioned — hooks, the status line,
settings. `--dry-run` shows the diff and writes nothing; `--yes` skips the confirmation.
See [Multiple accounts](accounts.md).

## `statusline`

Renders one Claude Code status line — model, cwd, git branch and worktree, context
pressure, and the 5-hour / 7-day rate-limit windows — from the JSON payload Claude Code
writes to stdin.

Install it from ⚙ Settings rather than wiring it by hand; if you do wire it by hand, point
`statusLine` in `settings.json` at:

```
"<python>" -m claude_sessions statusline
```

It runs on **every** conversation turn, so it is built to be cheap: the subcommand is
dispatched before the UI or the usage poller is imported, the branch is read straight from
`.git/HEAD`, and repo state comes from a disk cache that never spawns git. The rate-limit
and context numbers come from the payload Claude Code already sends — no network call is
ever made. Full detail on [Status line, failover & checkpoints](statusline.md).

## `--failover-serve` / `--failover-stop`

Run the local [model-failover proxy](statusline.md#model-failover) in the foreground, or
stop the background daemon named in the lock file.

```
archeus --failover-serve [port]   # run the proxy in the foreground
archeus --failover-stop           # terminate the daemon named in the lock file
```

Normally you turn it on in ⚙ Settings → Failover, which starts it as a detached child so
closing archeus does not leave every live session with connection-refused. It binds
`127.0.0.1` only and refuses any request carrying browser fetch metadata — it spends your
upstream quota, so a web page must not be able to reach it.

## Where its state lives

| Path | What |
|---|---|
| `~/.claude/archeus.json` | archeus's own settings — always read from `~/.claude`, independent of the config dir in use |
| `~/.claude/` | Claude Code's config dir. `CLAUDE_CONFIG_DIR` overrides it, and archeus follows it |
| `<project>/.archeus/memory` | that project's memory graph |

Everything else is in [Configuration](configuration.md).
