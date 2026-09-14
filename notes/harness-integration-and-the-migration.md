# The rename migration, and what the Codex / Pi CLI work has to know about it

Written for the session integrating other agent harnesses, because the two pieces
of work touch the same three seams and the failure mode is silent in both.

## What landed

`claude_sessions/migrate.py` finishes the move off the previous name. The first
pass renamed **paths**; this one covers what a rename could never reach.

| Seam | Entry point | When it runs |
|---|---|---|
| hook + statusLine commands whose script path is dead | `migrate.repair_commands()` | **every start**, ungated |
| `CLAUDE.md` sentinels, scheduler entry names | `migrate.sweep()` | once, behind `brand_sweep` |
| stale `CLAUDECTL_*` vars, a plugin under the old id | `stale_env_warning()`, `stale_plugin_warning()` | printed every start until acted on |

Both entry points are called from `main.run()`, inside the existing migration
`try` block — i.e. below every scriptable dispatch, so the statusline (which runs
on every conversation turn) and `--loop-run` never reach them.

## The four things to keep in mind

**1. `repair_commands` knows exactly one harness, and that is now a gap rather
than a simplification.** It walks Claude Code's `settings.json` through
`hooks._load` / `hooks._save`, finds any `.py` argument that no longer resolves,
and re-points it at this installation if the basename is one of ours. If Codex or
Pi CLI records an absolute path to an archeus script in *its* config — a hook, a
status line, a wrapper — that path dies in exactly the same circumstances (a new
venv, a moved checkout) and nothing will repair it. **Extend `repair_commands`
with the new config readers; do not write a second repair.** The identity rule
(dead **and** basename matches a file in this package dir) is what keeps it from
rewriting a fork's own scripts, and it is harness-neutral already.

**2. `claude_md.upsert_block` hardcodes `CLAUDE.md`.** It is the only writer for
all three machine-maintained blocks, it now writes atomically, and its seam
handling is the fiddly part (a plain slice grows a blank line on every rewrite).
If Codex gets `AGENTS.md`, **parameterise the filename on that function** rather
than copying it. The sweep does not need to follow: a block written into a new
file is born under the current name, so there is no old sentinel to clean up
there — `migrate.sweep()` deliberately walks `<project>/CLAUDE.md` and
`<cfgdir>/CLAUDE.md` only.

**3. `migrate.py` is the only module allowed to know the old name.** That is
enforced — `tests/test_no_old_brand_string.py` greps every tracked file against
the allowlist in `tools/_rename_brand.py`. A new harness adapter must not carry a
"read the old name too" fallback; if one is genuinely needed, it belongs in
`migrate.py` behind a flag, like everything else there.

**4. State stays harness-neutral, and it already is.** `store.WORKDIR` is
`.archeus` for every harness; `config.settings_file` is one file
(`~/.claude/archeus.json`, account-independent) and `brand_sweep` lives in it. Do
not give a new harness its own archeus settings file or its own workdir name —
the flag would then be per-harness and the sweep would run once per harness, and
the memory graph would fork.

## The plugin, and the final release under the old name

`plugin/` shells out to the `archeus` CLI on `PATH` and uses no
`${CLAUDE_PLUGIN_ROOT}`, so it is not coupled to the install and needs nothing
from the harness work. Its id is `archeus@archeus`; anyone still on
`claudectl@claudectl` is told so on startup.

`packaging/legacy-name/` is a metadata-only distribution that keeps the old PyPI
name alive: no code, one console script, one dependency. **Its pin must be the
NEXT archeus release, not the current one** — for a user holding both, upgrading
the old one uninstalls its own previous version, whose RECORD still lists the
shared `claude_sessions` files, so requiring a version they do not yet have is
what forces pip to put those files back.
`test_the_shim_pins_a_version_that_does_not_exist_yet` fails when the two numbers
meet, so bumping the release version means bumping that pin in the same commit.
Release order: archeus first, then the shim.
