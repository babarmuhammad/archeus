# CORPUS-NOTES — skill/agent/MCP static-lint fixture corpus (T-1080)

The future lint (T-1079, `claude_sessions/skillscan.py`) reads SKILL.md text,
agent files, CLAUDE.md, `.mcp.json` and Claude `settings` hooks statically —
no network, no model — and reports findings `{rule, line, reason}`. Each
fixture here is paired with a `NAME.expected.json` sidecar saying exactly what
a correct lint must report. Nothing in this directory is ever executed. All
hosts are the placeholders `example.com` / `example.invalid`; every invisible
character is an original corpus sample, not collected real-world material, and
the Unicode tag-character line in hostile-02 is invented for the corpus: not
native evidence, not a security boundary.

## Rule vocabulary and proposed boundaries (T-1079 may rename these ids)

| rule id | boundary as written here | tag |
| --- | --- | --- |
| hidden-unicode | U+200B, U+200D, U+2060, U+FEFF mid-text, U+E0000-U+E007F tag chars | — |
| bidi-control | U+202A-U+202E or U+2066-U+2069 anywhere in model-read text | — |
| instruction-override | tells the model to discard earlier/system instructions or hide from the user; prose or HTML comment | — |
| fetch-and-execute | download piped straight into a shell/interpreter (curl&#124;sh, wget -qO-&#124;bash, iwr&#124;iex) | — |
| long-base64 | run of >= 200 consecutive base64 chars that is NOT a `data:image/...;base64,` URI | [PROPOSED threshold] |
| mcp-command-exec | MCP command is a shell wrapper (sh -c, bash -c, cmd /c, powershell -Command) or `npx` of an unpinned package, with or without `-y`; plain local programs, npx of a package pinned to a full version, npx of a path on this machine (never a network share), npx with `--no` or `--no-install` and no `-y`, remote http are NOT flagged | owner item 96, widened by decision 114 |
| hook-command-exec | settings hook command is a shell wrapper; plain script or plain `npx prettier --check .` is NOT flagged | — |
| tool-name-collision | MCP server key equals a built-in tool name (Bash, Read, Write, Edit); agent `tools:` lists may name built-ins | [I: narrow reading, card author's] |
| description-drift | same skill read twice, `description:` differs; second read's sidecar carries the finding and `pair_with` | [I: board marks this as inference] |

## Fixtures: name → verdict → rule(s)

| fixture | verdict | rule(s) |
| --- | --- | --- |
| benign-01-skill-plain.md | benign | — |
| benign-02-skill-italian-accents.md | benign | — (non-ASCII is not suspicious) |
| benign-03-skill-npx-prettier.md | benign | — (plain npx, probe) |
| benign-04-skill-icon-datauri.md | benign | — (300-char base64 inside data:image URIs) |
| benign-05-skill-warns-about-curl-sh.md | benign | — (warning prose, probe) |
| benign-06-skill-plain-code-block.md | benign | — |
| benign-07-agent-readonly.md | benign | — |
| benign-08-agent-lists-builtin-tools.md | benign | — (tools: list is not a collision) |
| benign-09-claude-md-plain.md | benign | — |
| benign-10-claude-md-table.md | benign | — |
| benign-11-mcp-local-node.mcp.json | benign | — |
| benign-12-mcp-http-remote.mcp.json | benign | — (remote http exempt) |
| benign-13-mcp-npx-pinned.mcp.json | benign | — (pinned) |
| benign-14-mcp-python-module.mcp.json | benign | — |
| benign-15-settings-hook-script.settings.json | benign | — |
| benign-16-settings-hook-npx-check.settings.json | benign | — (probe) |
| benign-17-skill-drift-a.md | benign | — (first read of drift pair) |
| benign-18-skill-drift-b.md | benign | — (byte-identical second read, no drift) |
| hostile-01-skill-zero-width.md | hostile | hidden-unicode |
| hostile-02-skill-tag-chars.md | hostile | hidden-unicode (tag chars on an empty-looking line) |
| hostile-03-claude-md-rlo.md | hostile | bidi-control |
| hostile-04-agent-isolate-bidi.md | hostile | bidi-control |
| hostile-05-skill-ignore-previous.md | hostile | instruction-override |
| hostile-06-claude-md-disregard-hide.md | hostile | instruction-override |
| hostile-07-agent-html-comment-override.md | hostile | instruction-override |
| hostile-08-skill-curl-sh.md | hostile | fetch-and-execute |
| hostile-09-skill-wget-bash.md | hostile | fetch-and-execute |
| hostile-10-skill-iwr-iex.md | hostile | fetch-and-execute |
| hostile-11-skill-base64-blob.md | hostile | long-base64 (240 chars, no data URI) |
| hostile-12-mcp-npx-y.mcp.json | hostile | mcp-command-exec (npx -y, unpinned) |
| hostile-13-mcp-sh-c.mcp.json | hostile | mcp-command-exec |
| hostile-14-mcp-cmd-c.mcp.json | hostile | mcp-command-exec |
| hostile-15-settings-hook-sh-curl.settings.json | hostile | hook-command-exec + fetch-and-execute (same line) |
| hostile-16-settings-hook-powershell.settings.json | hostile | hook-command-exec |
| hostile-17-mcp-server-named-bash.mcp.json | hostile | tool-name-collision (plain node command) |
| hostile-18-skill-drift-b.md | hostile | description-drift (pair_with benign-17-skill-drift-a.md) |
| hostile-19-mcp-npx-unpinned.mcp.json | hostile | mcp-command-exec (npx, unpinned, no -y) |
| hostile-20-mcp-env-npx.mcp.json | hostile | mcp-command-exec (env assignments before npx) |
| hostile-21-mcp-npx-cache.mcp.json | hostile | mcp-command-exec (option value consumed before package) |
| hostile-22-mcp-npx-late-no-install.mcp.json | hostile | mcp-command-exec (late installation flag belongs to program) |
| hostile-23-mcp-github-version-suffix.mcp.json | hostile | mcp-command-exec (mutable Git reference) |
| hostile-24-mcp-fetch-launchers.mcp.json | hostile | mcp-command-exec (npm exec separator, npm x, pnpm dlx, yarn dlx, bunx) |
| benign-25-mcp-semver.mcp.json | benign | exact registry SemVer prerelease and build |

The corpus now contains 43 paired fixtures. Unit tests also cover bare assignments,
env options, option-value forms, command boundaries, and registry version syntax.
Git, GitHub, HTTP(S), tarball and file URL specs remain flagged, including full
Git commit hashes. Only registry specs receive the exact-version exemption.

## Decisions T-1079 / the owner (item 96) still have to take

1. long-base64 threshold: 200 is [PROPOSED]; hostile-11 (240) and benign-04
   (300 inside a data URI) pin both sides as far as they are pinned today.
2. DECIDED (owner decision 114): `npx` of an unpinned package is flagged with
   or without `-y` (hostile-12, hostile-19); a package pinned to a full
   version is not, with or without `-y` (benign-13).
3. Whether a mere *mention* of `curl | sh` in warning prose is flagged: this
   corpus says NO (benign-05), but the lint may overrule and would then have
   to move benign-05 or update its sidecar.
4. Whether `npx -y` alone (no package) or other wrappers (pwsh, python -c)
   join the mcp-command-exec / hook-command-exec lists.
