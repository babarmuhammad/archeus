# Track C handoff — code-simplifier plugin, then the simplification pass

Branch `chore/code-simplifier`, worked in the worktree `D:\archeus-simplify`. The primary
working tree (`D:\Claude`) was never touched.

## Phase 1 — plugin installed on every account

Target: `code-simplifier@claude-plugins-official` (one subagent, `model: opus`, no hooks, no MCP
servers, no slash commands). Reviewed from the marketplace clone before installing — three files:
`.claude-plugin/plugin.json`, `agents/code-simplifier.md`, `LICENSE`.

Installed through `plugins.install_plugin(..., cfgdir=<account>)`, which shells out to the real
`claude` CLI with `config.account_env(cfgdir)` — never by hand-editing `installed_plugins.json`.
The `claude-plugins-official` marketplace was already registered on all six accounts, so no
marketplace was added.

Verified by reading each account's own `installed_plugins.json` back through
`plugins.installed(cfgdir)`, not from the install command's output.

| Account | Result | Scope | Version | Install path exists |
|---|---|---|---|---|
| default | installed | user | 1.0.0 | yes |
| personal | installed | user | 1.0.0 | yes |
| Lorenzo | installed | user | 1.0.0 | yes |
| Gioele | installed | user | 1.0.0 | yes |
| Federico | installed | user | 1.0.0 | yes |
| Affan | installed | user | 1.0.0 | yes |

Six of six, no failures.

### The fan-out already existed — nothing was added to `plugins.py`

The prompt allowed a one-function addition if archeus could not already install a plugin across
every account. It can, from both surfaces, so nothing was written:

- GUI: `gui_api.api_plugin_install` iterates `_plugin_targets(..., scope='all')`, which defaults to
  `config.all_config_dirs()` — "adding defaults to every account, removing defaults to the one
  account you named".
- TUI/CLI: `provision.py` levels every account up to the union of what the others have, plugins
  included, behind the same review gate.

Every config dir is resolved inside a function taking `cfgdir`, so the import-time-binding bug
this codebase has paid for three times cannot recur here.

### One thing worth knowing about the agent itself

Its brief carries a "project standards" section written for a TypeScript/React codebase (ES
modules, arrow functions, explicit Props types) and an instruction to remove "unnecessary
comments". Neither applies here: archeus is stdlib-only Python, and its long module docstrings and
the CLAUDE.md gotchas are load-bearing institutional memory. The filter used in phase 2 rejects
both categories outright.

## Phase 2 — the simplification pass

See `notes/simplify-log.md` for the per-module accept/reject record.

*(filled in as the pass proceeds)*
