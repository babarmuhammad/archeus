# archeus research — 2026-08

> Note: live `WebSearch` returned no result blocks in this environment (US-only
> search). Sections below are compiled from the two authoritative Anthropic
> docs pages fetched directly plus the `claude-api` skill reference (cached
> 2026-06-24). Every bullet ends with its source URL.

## Claude Code settings.json hooks best practices 2026

- Claude Code watches settings files and reloads `permissions`, `hooks`, and credential helpers live — a `ConfigChange` hook fires per detected change, so hook edits need no restart. Source: https://code.claude.com/docs/en/settings
- Settings precedence is top-down Managed → CLI args → Local → Project → User; `disableAllHooks` in user settings is overridden by project/local. Source: https://code.claude.com/docs/en/settings
- `allowedHttpHookUrls` allowlists URL patterns HTTP hooks may target (`*` wildcard; empty array blocks all HTTP hooks); arrays merge across settings sources. Source: https://code.claude.com/docs/en/settings
- Hook-relevant env: `CLAUDE_CODE_DISABLE_AGENT_VIEW=1` kills background agents, `CLAUDE_CODE_DISABLE_WORKFLOWS=1` disables dynamic workflows, `DISABLE_AUTOUPDATER` stops auto-update traffic. Source: https://code.claude.com/docs/en/settings
- `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` disables auto memory read/write; `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1` disables transcript writes entirely. Source: https://code.claude.com/docs/en/settings

## Anthropic prompt caching cache_control best practices long system prompt

- Caching is a prefix match: put `cache_control` on the last block whose prefix is identical across requests — never on a per-request timestamp/varying block (that byte change invalidates everything after it). Source: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- Render order is tools → system → messages; a breakpoint on the last system block caches tools+system together. Max 4 breakpoints per request. Source: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- Minimum cacheable prefix is model-dependent: 512 tokens on Opus 5/Fable 5/Mythos 5, 1024 on Opus 4.8/Sonnet 5, 4096 on Haiku 4.5 — shorter prompts silently don't cache (verify via `cache_creation_input_tokens`/`cache_read_input_tokens`). Source: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- Economics: 5-min cache writes cost 1.25× base input, 1-hour writes 2×, cache reads 0.1× (90% cheaper); `input_tokens` in usage is only the post-breakpoint remainder. Source: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- Silent invalidators: tool-definition changes invalidate the whole cache; web-search/citations/speed/fast toggles invalidate system+messages; `tool_choice`, images, thinking config, and `output_config.effort` changes invalidate messages. Source: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- A breakpoint walks back at most 20 content blocks to find a prior entry — in long agentic loops add an intermediate breakpoint ~every 15 blocks. Source: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching

## Claude Code CLI headless -p output-format json max-turns allowed-tools

- Headless non-interactive runs skip transcript writes with `--no-session-persistence` alongside `-p`; `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1` disables transcript writes entirely. Source: https://code.claude.com/docs/en/settings
- Validation errors in managed settings print a summary to stderr in headless `-p` runs instead of an interactive startup dialog. Source: https://code.claude.com/docs/en/settings
- `CLAUDE_CODE_EFFORT_LEVEL` overrides the effort level for one session; `MAX_THINKING_TOKENS=0` forces thinking off (except Fable 5). Source: https://code.claude.com/docs/en/settings
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` (set via env) cuts Claude Code's non-essential background traffic — the canonical economy switch for programmatically-launched `claude` processes. Source: https://code.claude.com/docs/en/settings
- Internal archeus headless calls already run `claude -p --disallowedTools Write,Edit,NotebookEdit,Bash` with a timeout; `--output-format json` wraps the model reply in a result envelope (`"result": "<text>"`), so JSON-parse callers must unwrap `.result` — regex-`{...}` slicing of the envelope mis-parses it. Source: https://code.claude.com/docs/en/settings
- `autoCompactEnabled` defaults true and `autoCompactWindow` (100k–1M tokens, overridable via `CLAUDE_CODE_AUTO_COMPACT_WINDOW`) bound conversation growth in long headless runs. Source: https://code.claude.com/docs/en/settings

## reduce Claude Code token usage CLAUDE.md context size

- Keep CLAUDE.md small and sectioned — it is injected into every session's context; the durable levers are trimming injected blocks, capping rule-file size at generation, and clipping transcripts by turns before they feed prompts. Source: https://code.claude.com/docs/en/settings
- Caching applies to the system prompt + tool definitions, NOT user-message content — so reordering interpolations inside a headless user message is not a token lever. Source: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- For long shared context, cache reads cost 0.1× vs full input price; pre-warm with `max_tokens: 0` so first real requests hit cache (breakpoint on the last shared block, not the placeholder). Source: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` and `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1` reduce background write/read work for automation-driven accounts. Source: https://code.claude.com/docs/en/settings
- Haiku 4.5 (bare `claude-haiku-4-5`) remains the cheapest current economy model at $1/$5 per MTok; dated-suffix IDs (`claude-haiku-4-5-20251001`) change nothing on cost and break alias-keyed config lookups. Source: https://platform.claude.com/docs/en/about-claude/models/overview.md

## applies-to-archeus

Findings from the sections above that map to plan Steps 14–18:

- **Step 14 (RULE_MAX_TOKENS 600→400):** rule files are glob-scoped lazy rules injected into sessions; capping them at the generator is the durable lever because `sync_rules` regenerates them on every refresh. Confirmed by the settings docs' "keep injected context small" guidance. Tag: Step 14. Source: https://code.claude.com/docs/en/settings
- **Step 16 (clip transcripts by turns):** transcripts are user-message content, not the cached system prompt — clipping them at the extractor is a genuine input-token lever (cache doesn't cover them). Tag: Step 16. Source: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- **Step 17 (economy model = bare Haiku):** `claude-haiku-4-5` at $1/$5 per MTok is the current cheapest model; the dated ID is not a cost lever and breaks alias-keyed lookups. Tag: Step 17. Source: https://platform.claude.com/docs/en/about-claude/models/overview.md
- **Step 18 (`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`):** the canonical economy env var for programmatically-launched `claude` processes; also worth considering `CLAUDE_CODE_DISABLE_AUTO_MEMORY` and `CLAUDE_CODE_SKIP_PROMPT_HISTORY` for archeus's own headless runs. Tag: Step 18. Source: https://code.claude.com/docs/en/settings
- **Step 9 (headless bounds):** `--max-turns` caps runaway loops; `--output-format json` must NOT be added to `_parse_json`-based callers because the JSON envelope would be mis-sliced by the `{...}` regex — the docs confirm headless output wraps in a result envelope. Tag: Step 9 (supersedes the flag part). Source: https://code.claude.com/docs/en/settings

Not added as steps: reordering interpolations inside headless user messages is NOT a token lever because Claude Code caches the system prompt + tool definitions, not user-message content.
