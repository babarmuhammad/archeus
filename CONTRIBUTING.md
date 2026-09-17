# Contributing to archeus

Thanks for looking. **The memory and workspace layer for AI coding agents.** In practice
that is a terminal UI, a desktop GUI and a Claude Code plugin over one Python engine —
Claude Code is the agent it drives today. It has **zero runtime dependencies** and that
is a deliberate constraint, not an accident.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Getting set up

```bash
git clone https://github.com/babarmuhammad/archeus.git
cd archeus
python claude-sessions.py          # terminal UI
python claude-sessions.py --gui    # desktop GUI
```

There is nothing to build and nothing to install first. Python 3.10 or newer, and the
[Claude Code CLI](https://docs.anthropic.com/claude-code) for anything that launches a
session.

For the tests and the tooling:

```bash
python -m pip install pytest ruff        # tests and lint
python -m pip install -r requirements-docs.txt   # the docs site
```

## Before you open a pull request

```bash
python -m pytest tests/ -q       # the suite
python -m ruff check .           # lint
mkdocs build --strict            # only if you touched docs/ or mkdocs.yml
```

If you changed anything the GUI renders:

```bash
python tools/smoke_gui.py        # mounts, paints every page, parks the frame loop
python tools/shot_gui.py         # screenshots plus an overflow audit
```

If you changed the documentation site, a screenshot, or anything either published
site serves:

```bash
python tools/check_site_seo.py     # the BUILT html: titles, canonicals, JSON-LD, images
python tools/optimize_images.py --check
python tools/audit_site.py         # every page at 390x844 and 768x1024, nothing past the right edge;
                                   # every paragraph at 1440px, nothing past 96ch
```

If you changed anything under `www/` — a component, a page, `lib/` — the apex has
its own two, and CI runs both:

```bash
cd www && npm run lint     # eslint, including the react-hooks rules
cd www && npm run build    # the type check, and it prerenders every route
```

`npm run lint` is the one easy to forget, because `npm run build` passes without
it: a `useEffect` that calls `setState` in its body type-checks, prerenders and
renders correctly, and is rejected by `react-hooks/set-state-in-effect` — which
is right, and the fix (`useSyncExternalStore` for anything that is really an
external store) is usually simpler than what it replaces.

`check_site_seo.py` and `audit_site.py` read `site/`, so run `mkdocs build --strict`
first. The full sequence, and what a page owes beyond passing them, is in
`notes/seo.md`. `audit_site.py` and the two GUI tools need
`pip install playwright && playwright install chromium`; `optimize_images.py` needs
Pillow. All three run in CI — the first two on every push, the third on the weekly
schedule with the GUI smoke check.

### If you changed how the app LOOKS

Every published screenshot is generated, and a front-end change that does not
re-shoot them ships a manual showing an app that no longer exists. After a
change to layout, a skin or world, the stage, the nav, or a TUI screen:

```bash
py tools/shot_gui.py --docs     # every page + the published set, then export
py tools/shot_tui.py            # the two terminal frames
py tools/optimize_images.py     # derive the WebP siblings, re-compress
```

The guided tour is recorded the same way, and for the same reason — it is the
real app driven through the real steps, so it goes stale exactly when a screen
does. Re-record after a change to the nav, the dashboard, or the tour itself:

```bash
py tools/capture_tour.py        # the desktop app, as animated WebP
py tools/shot_tui.py --tour     # the same steps in the terminal
```

Both publish to `docs/img/` and `www/public/img/`. The recorder freezes the
background scene: WebP compresses between frames, so a moving background makes
every frame unique and the file is what a screen recording costs (860 KB
against 154 KB, measured). Pass `--live-motion` if you want the scene, and
check the image budget afterwards. Only the SHORT tour is published — a
thirty-seven step slideshow is not something anyone watches, and the long one
is walkable on the website instead.

The architecture animation only needs re-capturing when the graph itself
changes, and it must be shot from a CLEAN checkout named `archeus` — the
capture titles the graph after its directory and draws whatever is on disk, so
one taken in a working tree publishes your scratch files:

```bash
git worktree add ../archeus HEAD --detach
py tools/capture_graph_gif.py --project ../archeus --frames 30 --fps 12 \
    --width 900 --height 520 --out docs/graph-real.webp
cp docs/graph-real.webp www/public/graph-real.webp
git worktree remove ../archeus
```

Two things the tools decide for you, so do not fight them: the published
captures are taken in the **graph world** (`DOC_PAGES` in `tools/shot_gui.py`),
and both sites get the same files — `docs/img/` and `www/public/img/` — because
copying to one and remembering the other by hand is how the site ships a
release behind the manual.

**Do not hand-edit an image under `docs/img/`.** `tools/shot_gui.py` and
`tools/shot_tui.py` write the PNGs and `tools/optimize_images.py` derives the WebP the
manual actually links; `tests/test_demo_fixtures.py` rejects anything else in there.

## What the project cares about

**Zero runtime dependencies.** Everything the installed package imports comes from the
standard library. Test, docs and build tooling live in their own install steps —
`requirements-docs.txt` and the CI job that needs them — never in `pyproject.toml`.
PyQt6 is the one optional extra, and the GUI falls back to the browser without it.

**Read the gotchas first.** `CLAUDE.md` in the repo root documents the traps this
codebase has already fallen into: why animations may only touch `transform` and
`opacity`, why a module-level constant derived from mutable state is a cache with no
invalidation, why `settings.json` must be written atomically, why the statusline is
dispatched before `main` is imported. Most review comments on a first pull request are
already answered there.

**A gate nobody has watched fail is not a gate.** If you add a test that guards
something, break the thing on purpose once and confirm the test goes red. This repo
shipped a verification tool that printed `FAILURES: none` while executing zero checks;
several tests now exist specifically because of it.

**Tests stay in `tests/`, one file per area.** They use `pytest` and nothing else. TUI
screens are driven through the fake keyboard in `tests/harness.py`; the GUI is driven
through the stub server in `tools/smoke_gui.py`.

**Never put real data in a fixture.** Anything the screenshot tools are fed becomes a
published PNG, so the demo workspace is fictional by design —
`tests/test_demo_fixtures.py` fails the build if a fixture names a real home directory
or a real-looking absolute path.

**Documentation is part of the change.** A new feature updates its docs page,
`tools/smoke_gui.py` if it renders, and `docs/api.md` via `python tools/gen_api_docs.py`
if it adds a route. Generated files are never edited by hand.

## Commit messages

Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`), a
subject under about 50 characters, and a body that explains **why** when the reason is
not obvious from the diff. The commit log is used as project memory here, so a message
that records the reasoning is worth more than one that restates the patch.

## Reporting bugs

Open an issue with your OS, your Python version, `archeus --version`, what you
expected, and what happened. If a screen is involved, a screenshot helps — but check it
for project names or paths you would rather not publish first.

## Security

Please do not open a public issue for a security problem. Use GitHub's private
vulnerability reporting on the repository instead.

## The website

The marketing site (`www/`, Next.js) and the documentation (`docs/`, MkDocs Material)
both live in this repository and both deploy from `main`. The zero-dependency rule
applies to the Python package — the website has its own `package.json` and that is fine.
