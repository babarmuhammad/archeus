# Four parallel tracks — the partition, so four sessions do not collide

Four agents, four accounts, one repo. Each track's prompt is a file in this directory: paste
the whole file as the first message of a fresh session.

| Track | File | Branch | Account |
|---|---|---|---|
| A — site legal, compliance, Ko-fi | `track-a-legal-compliance.md` | `legal/site-compliance` | |
| B — zoetrope session flow graph | `track-b-session-flowgraph.md` | `feat/session-flowgraph` | |
| C — code-simplifier plugin | `track-c-code-simplifier.md` | `chore/code-simplifier` | |
| D — account rotation daemon | `track-d-account-rotation.md` | `feat/account-rotation` | |

## A fifth agent is already working, on `main`

Not one of these four. It is mid-task in the primary working tree (`D:\Claude`), with
uncommitted changes and commits not yet pushed. Treat `main` as **moving**, not as a fixed base.

Rules for all four tracks:

- **Never touch the primary working tree.** No `git add`, commit, stash, checkout, reset,
  `clean`, or branch switch in `D:\Claude`. You work only inside your own worktree.
- `git worktree add` branches from the last **commit**, so the main worker's uncommitted edits
  are not in your tree. That is correct — do not try to pull them in.
- **Files currently in flight on `main`** (as of writing): `claude_sessions/gui_api.py`,
  `claude_sessions/web/app.js`, `claude_sessions/web/index.html`, `gui.py`, `main.py`,
  `harnesses.py`, `codex.py`, `pi.py`, `tests/test_codex.py`, `tests/test_harnesses.py`,
  `tests/test_launch_integration.py`. Any version of these you read is provisional.
- **Tracks B and D append into `gui_api.py` and `web/app.js`, which the main worker is editing
  right now.** Expect a three-way conflict at merge. Resolve it by re-appending your entry at
  the end of the table as it stands after main's change — never by taking a whole-file side.
- **Track B** reads `harnesses.py`, `codex.py` and `pi.py` to decide whether Codex and pi
  sessions can be supported. That code is live on main this minute. Confirm the transcript shape
  against merged main before you commit support for it.
- Before opening a PR: `git fetch && git rebase origin/main`, then re-run your full gate list.
  Main will have moved since you branched.

## Isolation

One worktree per track. Do not run two of these in the same working tree, and do not use
`D:\Claude\.claude\worktrees\` — that directory is archeus's own worktree pool.

```
git worktree add ../archeus-legal    -b legal/site-compliance
git worktree add ../archeus-flow     -b feat/session-flowgraph
git worktree add ../archeus-simplify -b chore/code-simplifier
git worktree add ../archeus-rotate   -b feat/account-rotation
```

## File ownership

| Track | Owns | Never touches |
|---|---|---|
| **A** | `www/**`, `docs/*.md`, `mkdocs.yml`, `README.md`, `.github/FUNDING.yml`, `pyproject.toml` (urls), `packaging/**` (funding fields), `tools/check_site_seo.py`, `tests/test_site_links.py`, `tests/test_site_legal.py` | any `claude_sessions/**` |
| **B** | new `claude_sessions/flowgraph.py`, new `web/flow.js` + `flow.css`, `tests/test_flowgraph.py`, `docs/sessions.md` | `www/**`, quota/accounts/usage/failover, `README.md`, `packaging/**` |
| **D** | `quota.py`, `usage.py`, `accounts.py`, `failover.py`, new `rotate.py`, `tests/test_rotate.py`, `docs/accounts.md`, `docs/providers.md` | `www/**`, `connections.py`, `flowgraph.py`, `gui.py`, `README.md`, `packaging/**` |
| **C** | plugin install (no repo code) + phase-2 simplify on a named allowlist | everything A/B/D own, until merged; and all prose |

## Rules for the shared hot files

`gui_api.py` (`GET_ROUTES` ~4383, `POST_ROUTES` ~4459), `web/app.js` (`NAV` line 754),
`app.css`, `CHANGELOG.md`, `docs/img/`:

- **Append only, at the end of the existing table.** No reorder, no reformat, no edits to
  adjacent lines.
- **Nobody edits `CHANGELOG.md`.** Each track writes `notes/handoff-<track>.md` instead; the
  integrator folds them in at merge.
- **Nobody re-shoots screenshots.** One `py tools/shot_gui.py --docs` run after all merges,
  then `py tools/shot_tui.py` and `py tools/optimize_images.py`. Otherwise four tracks rewrite
  the same PNGs.
- Each track gets its **own** new test file. Never edit another track's.

B and D are the only two that both touch `gui_api.py` and `app.js` — append-only at different
anchors, and D merges first.

## Merge order

**main worker (continuous) → A → D → B → C.**

C runs last because phase 2 rewrites code the other three wrote. A runs first because it carries
the funding and package metadata the others must not touch. The main worker lands whenever it
lands; all four rebase onto whatever it has pushed.

## Blocking answers to supply before launching

- **Track A** needs the Ko-fi handle, the operator identity and contact route, the jurisdiction,
  and whether any donation tier or perk is planned. Without the handle it commits a
  `<KOFI_USERNAME>` placeholder.
- **Track D** needs a decision on credentials. Rotating mid-session means reading another
  account's OAuth token and injecting it, which contradicts this repo's read-only credential
  policy — refreshing can lock an account out of Claude Code. The prompt tells the agent to stop
  and ask. Answer it up front or it stalls.

## Ko-fi — the steps no agent can do

1. Create the Ko-fi page at ko-fi.com and pick the handle. That handle goes into four package
   registries and the URL is permanent — choose carefully.
2. Connect payouts (Stripe or PayPal) in Ko-fi settings. Without it the page takes nothing.
3. Turn **off** shop, commissions and memberships unless you want them. Tiers and perks are
   exactly what converts a donation into a consumer supply contract and pulls in refund rights.
   Off keeps the legal surface small.
4. Fill the page description so it matches what the site says. Two contradicting descriptions is
   its own problem.
5. The GitHub Sponsor button appears automatically once `.github/FUNDING.yml` is on the default
   branch — nothing to click.
6. Hand Track A the handle, or it commits the placeholder and blocks.

Tax treatment of donations depends on where you are established. Track A's risk register files
it under "Needs a lawyer" and that is where it should stay.
