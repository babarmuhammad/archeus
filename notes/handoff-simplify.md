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

Ran early, deliberately. The brief gates phase 2 on the other three branches being merged; at the
time of writing none has a commit (`legal/site-compliance` does not exist, the
`feat/session-flowgraph` and `feat/account-rotation` worktrees sit at `main`'s HEAD) and the
primary tree still has uncommitted work. The user chose to run the full phase anyway, accepting
the merge-conflict risk. Every other fence held: nothing outside the allowlist was touched, and
`D:\Claude` was never written to.

**33 files, 280 insertions, 276 deletions, 35 commits — one per module.** The line count is the
least interesting number here. What came out is duplication of things that must not drift:

- one definition of a character's display width (`render.py`), where two copies fed every width
  calculation in the TUI;
- one definition of the zero-width/bidi class in `skillscan.py`, where the rule that FLAGS it and
  the sanitiser that STRIPS it had separate copies — drift there means the report re-emits the
  character it just warned about;
- one definition of "the same rule" in `conventions.py`, where the module's own contract is that
  pinning pins exactly what the clustering counted;
- one lenient snapshot reader in `diffview.py`, replacing three copies that each leaked a handle;
- one percentile and one event mark in `probe_qt.py`; one render gate in `shot_gui.py`, where the
  copy that stops gating is the one that reports `clean` for measuring nothing.

### Rejected, and why it is the more useful half

Ten proposals were refused. The pattern worth carrying forward: **a diff whose only risk is
transcription, on a file that generates a committed artifact, is not worth taking** — that killed
the `gen_api_docs` markdown constant and the `gen_cluster_spec` `main()` split. Also refused: a
`_drive` helper for two callers, dropping a `sorted()` that made a function self-sufficient, a
scan-merge that reordered failure output, and both edits proposed inside `smoke_gui.py`'s
`with sync_playwright()` block. The agent's own house-style section (ES modules, arrow functions,
React props) was ignored wholesale — it describes a TypeScript codebase, and its instruction to
remove "unnecessary comments" is a regression here, where the docstrings are institutional memory.

Per-module detail, including every rejection, is in `notes/simplify-log.md`.

### Two defects found, one fixed

- **Fixed:** `tools/inspect_cluster.py` hardcoded `D:\Claude` into `sys.path`, so in any other
  checkout — this worktree included — it imported the *other* tree's `stage.js` and `gui.py`. It
  graded a copy, which is exactly what its docstring says it exists to avoid.
- **Flagged, not fixed:** `claude_sessions/migrate.py:253` compares a repointed string against the
  **raw** dict value, so a hook whose `command` is missing or not a string always compares unequal,
  is coerced to `''`, records a bogus `moved` entry and triggers a `hooks._save` on a start-up
  path. The statusLine branch twelve lines below already does it the safe way. Fixing it is a
  behaviour change, which this pass does not make — it is the module owner's call.
- Also flagged: two `check(...)` calls in `smoke_gui.py` pass a detail argument that is always the
  empty string (`txt[:0]`), so a failure there prints no diagnostic. Restoring a real `[:200]` is a
  change to failure output, so it was left alone.

### Verification

`py -m pytest -q` → **2335 passed, 1 skipped**, identical to the baseline taken before any edit.
`ruff` clean (and its `F821` caught a missed rename in `gen_plugin.py` before anything ran).
`py tools/smoke_gui.py` → **319 checks, JS errors none, FAILURES none**. `mkdocs build --strict`
exit 0. All four generator `--check`s report their committed output current, so no generated file
moved. `probe_qt.py`'s two embedded scripts pass `node --check`.

One environment note, because it cost three runs: `smoke_gui.py` binds a fixed port, a crashed
earlier run left a server listening on it, and the next three runs failed with
`ERR_CONNECTION_REFUSED`/`ERR_CONNECTION_RESET` on a *different* set of checks each time —
including one that looked exactly like a regression in a stub this pass had edited. The committed
tree failed the same way, which is what identified it. Kill the stale listener before believing a
failure there.

### For the integrator

- `tools/check_site_seo.py` is on **Track A's** owned list and this branch touches it (four lines
  in a print statement). Expect a conflict; re-apply on top of A rather than taking a side.
- No screenshots were re-shot, no `CHANGELOG.md` edit, no version bump, nothing published.
- CHANGELOG lines to fold in at merge:

```
### Changed
- Removed duplicated definitions across the TUI, the scanners and the tooling: one display-width
  rule, one hidden-character class, one convention-overlap threshold, one snapshot reader, one
  render gate. No behaviour change; the full suite is unchanged at 2335 passing.

### Fixed
- `tools/inspect_cluster.py` inspected a hardcoded checkout path rather than the tree it runs in.
```
