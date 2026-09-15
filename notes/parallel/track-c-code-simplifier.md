# Track C — install the code-simplifier plugin everywhere, then use it

Paste this whole file as the first message of a fresh session.

---

You are working in the archeus repo (D:\Claude) on branch `chore/code-simplifier`, in a
dedicated git worktree. Three other agents are working the same repo in parallel on
`legal/site-compliance`, `feat/session-flowgraph` and `feat/account-rotation`.

**A fifth agent — not one of the four — is already working directly on `main`,** in the primary
working tree (`D:\Claude`), with uncommitted changes and unpushed commits. Treat `main` as
moving, not as a fixed base:

- **Never touch the primary working tree.** No `git add`, commit, stash, checkout, reset, clean
  or branch switch in `D:\Claude`. Work only inside your own worktree.
- Its work is in `claude_sessions/gui_api.py`, `web/app.js`, `web/index.html`, `gui.py`,
  `main.py`, `harnesses.py`, `codex.py`, `pi.py` and three test files. None of those are on your
  phase-2 allowlist, and they must stay off it — do not simplify a file another agent is
  actively editing, even after it lands.
- Phase 1 (installing the plugin across accounts) touches no repo code and can run at any time.

This task has two phases. **Phase 2 must not start** until those three branches are merged into
`main`, the fifth agent's work is committed and pushed, and you have rebased onto the merged
`main`. If you cannot confirm all of that, do phase 1, report, and stop.

## Phase 1 — install the plugin on every account (no repo code changes)

Target: plugin `code-simplifier` from marketplace `claude-plugins-official`
(https://github.com/anthropics/claude-plugins-official). It ships one agent that simplifies and
refines recently-modified code for clarity, consistency and maintainability while preserving
functionality.

1. Enumerate every configured account. archeus already knows them — `claude_sessions/accounts.py`
   plus `config.all_config_dirs()`. Do not hand-maintain a list.
2. For each account config dir, with `CLAUDE_CONFIG_DIR` set to it, shell out to the real CLI.
   NEVER hand-edit the caches:
   ```
   claude plugin marketplace add anthropics/claude-plugins-official
   claude plugin install code-simplifier@claude-plugins-official
   ```
   `known_marketplaces.json` and `installed_plugins.json` are Claude Code's own state, their
   format has already changed once, and archeus's standing rule is that every plugin mutation
   goes through the CLI. Read `claude_sessions/plugins.py` first — the provenance index and the
   on-disk format are documented there.
3. Import-time binding is this codebase's recurring bug and it has cost the per-account features
   three times. Anything you write that resolves a config dir must do so in a FUNCTION taking
   `cfgdir`, never a module-level constant. Use the existing `across_accounts(fn)` fan-out if you
   add code at all.
4. Verify by READING BACK from each account's `installed_plugins.json`, not from the install
   command's own output. Report a per-account table: installed / already present / failed with
   reason.
5. If archeus's own plugin manager cannot already do this fan-out from the TUI and the GUI, that
   is a legitimate one-function addition to `claude_sessions/plugins.py` — but propose it in the
   handoff first. Do not build it unasked.

## Phase 2 — simplify the codebase (only after the three merges)

Read this before you touch anything. archeus already runs a code-minimisation regime: the
`ponytail` skill, `minimalcode_hook.py`, and the ladder in CLAUDE.md. The code-simplifier agent
is an ADDITIONAL reviewer, not a mandate to rewrite. The long explanatory module docstrings and
the dense CLAUDE.md gotchas are load-bearing institutional memory — they are NOT verbosity to be
simplified away. Deleting one is a regression.

Method, one module at a time:

1. Pick ONE module. Run the code-simplifier agent over it. Capture its proposals.
2. Filter. Accept only changes that are behaviour-preserving and reduce real complexity. REJECT
   anything that removes a guard, a validation, an error path, a security check, an accessibility
   affordance, a comment explaining WHY, or a test. Reject "consistency" rewrites that produce a
   large diff for no behaviour change.
3. Apply, run the FULL suite, commit that module alone. One module per commit, so any regression
   bisects to one file.
4. Record in `notes/simplify-log.md`: module, proposals, accepted, rejected and why.

**Allowlist — work these in this order, and nothing else without asking:**

```
claude_sessions/render.py, diffview.py, search.py, health.py, conventions.py,
migrate.py, notify.py, review.py, skillscan.py, denygen.py, hookrules.py
tools/*.py
```

**Do NOT simplify:** `gui_api.py`, `gui.py`, `web/app.js`, `web/app.css`, `connections.py`,
`cluster_spec.py`, any stage or scene code, `transcripts.py`, `store.py`, `proc.py`,
`jsonstore.py`, `config.py`, `quota.py`, `failover.py`, `gateway.py`, `proxy_base.py`,
`hooks.py`, `statusline.py`, `checkpoints.py`, or anything under `tests/`. Those are hot,
security-relevant, freshly rewritten by another branch, or protected by AST gates whose
invariants a simplifier does not know about.

**Also do NOT simplify:** `README.md`, `.github/FUNDING.yml`, `pyproject.toml`, `packaging/**`,
`www/**`, `docs/**`. Legal and funding copy is not code — a "simplification" of a policy
sentence or a donation disclaimer changes its legal meaning. Leave prose alone entirely.

## Verify after every single commit

```
py -m pytest -q
py -m ruff check claude_sessions tools
py tools/smoke_gui.py
```

No new failures and no skips added. If the suite goes red, revert that commit rather than
patching the test.

## Handoff

`notes/handoff-simplify.md` — the per-account install table, a summary of the accept/reject log,
total lines removed, and anything you flagged but did not touch.

Do not edit `CHANGELOG.md`. End every commit message with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
