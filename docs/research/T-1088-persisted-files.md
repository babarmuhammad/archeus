# T-1088 — Inventory of every file Archeus persists into a project or user config

Card: T-1088 · Date: 2026-11-09 · Repository snapshot: the MXC integration branch,
tip `6473ada0` — transcribed from the card; this container has no git binary, so the
tip itself is not re-confirmed here [?].

Background caveat: the apiiro blog post "coding agents leaking secrets" (Hacker News
item 50407882) is a secondary source and was not re-read for this card. It says Claude
Code's "Don't ask again" stores the FULL approved shell command, inline passwords
included, as an allow rule in `.claude/settings.local.json`. Claude Code writes that
file, not Archeus, so Archeus cannot prevent that write; it can only avoid doing the
same thing itself. This note therefore inventories what ARCHEUS writes into a project
or user config, and what its one shared secret filter catches and misses:
`archeus/core/redact.py` — `SECRET`, compiled at :51 from the alternation at :33-50,
and `redact(text)` at :54-55 (`SECRET.sub` replaces each match with `[redacted]`).
The legacy package imports that module in exactly one place, claude_sessions/
events.py:34 (a whole-package grep finds no other import); no writer below does.

**Nothing here is native evidence; this is a reading of source.**

Every `hunter2`-style string mentioned in this note or in the corpus is a placeholder
on the example.com host, never a real credential.

Legend: `[?]` could not confirm by reading · `[I]` the reader's own inference. Every
other claim carries a file:line opened in this snapshot. Consecutive source lines are
never quoted more than three.

## The table

| # | writer (function, file:line) | path written (pattern) | inside a git tree? | gitignored (by what, file:line, or "no") | redacted? | what text goes in |
|---|---|---|---|---|---|---|
| 1 | health.propose_allowlist — claude_sessions/health.py:192; write `_c.write_atomic(sp, ...)` :217 after `diffview.confirm` :215 | `<project>/.claude/settings.json` → `permissions.allow` | yes (project root) | no — `config._ensure_dir` seeds a marker only for base name `.archeus` (claude_sessions/config.py:750); `.claude` gets none | n/a (see last column) | the lowercased FIRST WORD of Bash commands from this project's transcripts (health.py:185-187), as `Bash(<word>:*)` rules; words pass `re.fullmatch([a-z0-9_.-]+)` (health.py:187), so a whole command line — the apiiro shape — cannot enter this file via this writer [I] |
| 2 | denygen.merge_deny — claude_sessions/denygen.py:71; `_c.write_json_atomic(sp, data)` :96 | `<project>/.claude/settings.json` → `permissions.deny` | yes | no (same basename test, config.py:750) | n/a | `Read(...)` patterns for heavy dirs and lock files actually present; the vocabulary is fixed names (denygen.py:16-19 — the card's "12-17" is these, a few lines off), patterns built at :53,:59; only project-relative paths of existing entries vary [I] |
| 3 | ccsettings.write — claude_sessions/ccsettings.py:204; through hooks._load (hooks.py:630) / hooks._save (hooks.py:639-640) | `<account cfgdir>/settings.json` (hooks.settings_path_for, hooks.py:596-607) | no — an account config dir, not a checkout [I] | n/a (not in a tree) | no | one schema-typed key per call, value coerced by `SCHEMA` (ccsettings.py:33+); kinds `str`, `list`, `json` can still carry arbitrary strings, e.g. `autoMode` (ccsettings.py:63-65) [I] |
| 4 | hooks install — install_memory_hook hooks.py:403, install_worklog_hook :467, install_limit_hook :541, add_hook :1091; all write via `_save` hooks.py:639-640 | `<account cfgdir>/settings.json` → `hooks` block | no [I] | n/a (not in a tree) | no — `add_hook` stores the command verbatim, no redact call (hooks.py:1107,1119) | the three installers write `"<python>" "<script path>"` commands (hooks.py:397-400, :454-457, :535-538); `add_hook` additionally stores one hand-AUTHORED command string from the user, verbatim |
| 5 | logbash_hook, PostToolUse — claude_sessions/logbash_hook.py:55-78; plain `open(p, 'a')` :76 (card's ":66" is this, a few lines off) | `<project>/.archeus/bash-log.txt` | yes | yes — `.archeus/.gitignore` holding `*`, seeded through store.workdir → `config._ensure_dir` (store.py:26-38, config.py:750-760) | no | every raw Bash command Claude Code ran in the project, appended verbatim (:76-77); store.py's own docstring names this risk — `export TOKEN=…` living in bash-log.txt (store.py:30-32) |
| 6 | automode.record — claude_sessions/automode.py:200; append :210 | `<project>/.archeus/denied.jsonl` | yes | yes — same route (automode.py:205 → store.py:37 → config.py:750-760) | no | one JSON per denial: `{ts, tool, command[:500], reason[:300]}` (automode.py:207-209); the command is the tool's command/file_path/path/url/pattern field (logbash_hook.py:36-46) |
| 7 | worklog.save_worklog — claude_sessions/worklog.py:43-44; write via `config.write_json_atomic` → `write_atomic` (config.py:766, `_ensure_dir` at :789) | `<project>/.archeus/memory/worklog.json` (worklog.py:33-36; `store.workfile` is a pure join, store.py:44-55) | yes | NOT by this write — `_ensure_dir` checks only `basename(d) == '.archeus'` (config.py:750) and here the dir it is asked to create is `.archeus/memory`, base name `memory`; covered only if an earlier writer already seeded the marker [I] | no | one entry per session: `summary` = the AI title or the FIRST USER MESSAGE capped at 120 chars (worklog.py:159,182-184), relative paths of edited files, `last_error[:120]` from a failed tool result (:181), via capture_session (:207-247) |
| 8 | memrules.sync_rules — claude_sessions/memrules.py:112-156; `os.makedirs` :127, plain `open(p, 'w')` :144 | `<project>/.claude/rules/archeus-mem-*.md` | yes | no — plain `os.makedirs` (:127) never reaches `_ensure_dir`; the marker exists only for `.archeus` (config.py:750) | no | rendered rule bodies (`render_rule` memrules.py:80, called :134): entity names/notes and module summaries from the memory graph — user-derived text |
| 9 | claude_md memory block — upsert_block claude_sessions/claude_md.py:38 (`_c.write_atomic(md_path, new)` :81), write_memory_block :86, loop over `instructions_files()` :107 | `<project>/CLAUDE.md`, `<project>/AGENTS.md` (every instructions file) | yes | no — these files are meant to be committed [I]; no marker mechanism applies at the project root | no | the ARCHEUS:MEMORY block, one digest from the memory graph (claude_md.py:103-106) |
| 10 | context_inject — `_write_context_file` claude_sessions/context_inject.py:53-76; second file via `store.workfile` :179-180, actually written by system_prompt.merged_system_prompt (claude_sessions/system_prompt.py:11-28) | `<project>/.archeus/injected-context.md` (CTX_FILE, context_inject.py:13) and `<project>/.archeus/context-system-prompt.txt` | yes | no — both writers call `os.makedirs` themselves and never `_ensure_dir` (context_inject.py:72, system_prompt.py:23); covered only if an earlier writer seeded the marker [I] | no | the WHOLE prior transcript — every user and assistant message text (context_inject.py:65-69) — and the merged system prompt plus a pointer line (system_prompt.py:25) |
| 11 | V1 `res/settings.json` — `_settings` archeus/harnesses/claude_code/adapter.py:156-174; `config.write_json_atomic` :173 | `<exec dir>/res/settings.json`, exec dir under `<ARCHEUS_HOME>/run/exec/<id>/` (archeus/infra/paths.py:272-289) | no — Archeus's own run tree [I] | n/a (not in a tree) | n/a | `hooks`: PreToolUse/PreCompact commands joined from `spec.hook_settings` (:160-166) plus `skipWebFetchPreflight` (:171); Core-authored argv, no user text (card claim, confirmed by reading the function) [I] |
| 12 | [found] sources.flag_argv — archeus/harnesses/sources.py:392-405; `config.write_atomic` :401-402 (`mode=0o600`) | `<exec dir>/mcp.json` (`MCP_CONFIG`, archeus/infra/paths.py:269) | no [I] | n/a (not in a tree) | no | the opted-in MCP server DEFINITIONS copied verbatim from the user/project MCP files (sources.py:380-388); paths.py:269-270 calls this file "the opted-in MCP servers, keys included (T-099)". The sources.py docstring's redaction promise (:17-19) covers the inventory RECORD only, not this written file. Found while checking sources.py as the card asked; listed though it is a Core run-dir config, not project/user config, because it persists secret material |

Row 4's `add_hook` and rows 5, 6, 10 are the apiiro question localised: Archeus does
not create `.claude/settings.local.json`, but it does persist command- and user-text
in files it does create.

## redact.SECRET today

Families in `SECRET` (archeus/core/redact.py:33-50, compiled :51), each confirmed by
reading those lines:
- minted token prefixes from `ids.TOKEN_PREFIXES` (:34); `sk-` / `sk-ant-` (:35); `gsk_`/`sk_live_`/`sk_test_`/`rk_live_`/`npm_` (:36)
- `gh[pousr]_` / `github_pat_` / `glpat-` (:37); `AKIA`/`ASIA` AWS ids, `AIza`, `xox…-` (:38)
- `Bearer <token>` (:39); `Authorization: Basic <b64>` (:40); JWTs `eyJ…` / `.eyJ…` (:41-43); PEM private-key blocks (:22-27, :44)
- URL userinfo `://user:pass@` and `://longname@` (:45-46); `-u` / `--user user:pass` (:47)
- the keyed `aws_secret_access_key` — the ONE keyed rule, and it needs `=` or `:` after the name (:49-50)
It LACKS any rule keyed on a password-like NAME: `PGPASSWORD=`, `--password x`,
`-pSECRET`, `export TOKEN=<opaque>` all stay in clear (lines 33-50 read in full).
Corpus (tests/fixtures/persisted_secrets/commands.json, 37 cases): 12 `caught`,
17 `missed`, 6 `benign_ok`, 2 `benign_overredacted`.

## (a) rows with `redacted? = no` whose text can carry free user or command text

Rows 4 (`add_hook` hand-authored command), 5 (raw Bash commands — this is exactly the
apiiro shape, in Archeus's own file), 6 (denial command[:500] + reason[:300]),
7 (first user message and tool error text), 8 (memory-graph text), 9 (memory digest),
10 (the whole prior transcript); plus row 3 [I] (schema `str`/`list`/`json` values)
and row 12 (MCP definitions copied verbatim — credential material rather than free
text). None of the ten writer files contains a call to `redact` (grep: zero hits
across logbash_hook.py, automode.py, worklog.py, context_inject.py, memrules.py,
claude_md.py, health.py, denygen.py, hooks.py, ccsettings.py).

## (b) rows whose gitignore cover could not be established

Rows 7 and 10. Both land under `<project>/.archeus/` without seeding the marker
themselves: row 7's `write_atomic` → `_ensure_dir` call asks for `.archeus/memory`,
whose base name is `memory`, so the `basename == '.archeus'` test (config.py:750)
fails; row 10 calls `os.makedirs` directly and never reaches `_ensure_dir` at all
(context_inject.py:72, system_prompt.py:23). Whether `.archeus/.gitignore` exists
when they first write depends on an earlier writer — `store.workdir` (store.py:37) or
any `write_atomic` whose target directory is `.archeus` proper (rows 5 and 6 always
seed it when they run) — and that ordering is not guaranteed by anything I read.

## (c) things I could not decide, with the one fact each needs

- Whether every real project has `.archeus/.gitignore` before row 7 or 10 first
  writes. Need: one install/session-start step that guaranteed creates `.archeus` —
  none found by reading [?].
- Whether Claude Code itself gitignores anything under a project's `.claude/`
  (affects rows 1, 2, 8). Need: Claude Code's own init behaviour — an external
  binary, not in this checkout [?].
- Whether the `autoMode` `json` editor can carry secret values into row 3. Need: the
  UI-side validation for that key; `ccsettings.py:63-65` declares kind `json` with no
  content check [?].
- The repository tip `6473ada0` itself. Need: a git binary (this container has
  none) [?].

Confirmed: archeus/harnesses/sources.py is NOT a writer of a project or user settings
file — it only READS `.claude/settings.local.json` (the `local` source mapping,
sources.py:250-252, consumed read-only via `_json` :104 in the loop at :296-305); its
one write is the execution's own `mcp.json` (:396-402), row 12. Also confirmed:
nothing in claude_sessions/ or archeus/ writes `.claude/settings.local.json` at all
(grep over both packages: the only other mention is automode.py:13, a docstring about
reading it).

## Hint corrections (the card's hints, confirmed or corrected by opening each place)

denygen "fixed names, lines 12-17" → actually denygen.py:16-19 (card allows "off by a
few"). logbash_hook "55-70, open at 66" → the append is logbash_hook.py:76-77;
`_rotate` is :91, 64 KiB cap at :87. Everything else opened where the card said:
health.py:172-219, ccsettings.py:204-228, hooks.py:397-423/454-490/535-570/1091-1130/
630-640, automode.py:200-215, worklog.py:33-44/121-193/207-250, memrules.py:80/112-156,
claude_md.py:30-83/86-111, context_inject.py:53-75/172-180, adapter.py:157-175,
store.py:26-57, config.py:738-760/763-800, redact.py:33-51/54, events.py:34.
