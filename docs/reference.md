---
description: >-
  How archeus generates CLAUDE.md, how Claude Code encodes project paths into folder
  names, and where the rest of the file reference now lives.
---

# Files, layout & encoding

Two mechanisms that are neither configuration you set nor a feature you use: how
`CLAUDE.md` is written, and how a project path becomes a folder name.

!!! info "The rest of this page moved"

    Per-project files, the global `CLAUDE.md` and the repository layout are now on
    [Configuration](configuration.md). The workspace provenance manifest is on
    [Projects](projects.md#workspace-status). This URL is kept because it is linked from
    outside the site.

## CLAUDE.md auto-generation

**`c` — Scaffold (fast, mechanical)** builds CLAUDE.md from:

- Git repos found up to 2 levels deep in the project and any linked extra paths
- Last 7 commits from each repo (`git log --oneline -7`)
- First 15 lines of each repo's README
- All session topics (accumulated, never discarded)

On an existing file, only the `<!-- AUTOGEN:START -->…<!-- AUTOGEN:END -->` and
`<!-- SESSIONS:START -->…<!-- SESSIONS:END -->` blocks are replaced. Everything outside those
blocks is preserved exactly.

**`a` — AI analyze (slower, comprehensive)** runs `claude.exe -p` with a rich prompt
containing the full directory tree, git history, READMEs, extra paths, and session history.
Claude writes the entire CLAUDE.md. You review it in a pager and approve or reject before any
file is written.

On an existing file, the current content is passed as ground truth with instructions to
update only facts that have clearly changed. After generation the
`<!-- AUTOGEN:START/END -->` and `<!-- SESSIONS:START/END -->` blocks are injected
mechanically, and `<!-- AI:ANALYZED -->` is inserted on line 2 so future runs enter update
mode rather than fresh mode.

## Session encoding

Claude Code encodes project paths as folder names under `~/.claude/projects/` by replacing
path separators with `--` and certain special characters with `-`. For example:

```
D:\Projects\my-app  →  D--Projects-my-app
```

The encoding is lossy, so `find_actual_path()` in `paths.py` does not try to decode it. It
reads the real path out of the `cwd` field that every transcript line already records, and
only falls back to walking the filesystem and matching encoded components (handling `_`,
`+`, `-`, `#` in directory names) when a project folder has no transcript to read. That
ordering is what makes UNC paths work: `\\server\share\Project` encodes to
`--server-share-Project`, which no amount of splitting on `--` can turn back into a drive
letter.

## See also

- [Configuration](configuration.md) — every file archeus reads and writes
- [Projects](projects.md) — health checks and the workspace freshness manifest
- [API reference](api.md) — the HTTP routes the desktop app is built on
