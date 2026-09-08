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

Both need `pip install playwright && playwright install chromium`.

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
