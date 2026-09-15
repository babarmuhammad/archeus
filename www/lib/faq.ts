/**
 * The FAQ, once. The page renders it and the FAQPage JSON-LD is generated from
 * the same array, so the structured data can never describe questions the page
 * does not answer. (Ported from docs/faq.md, whose hand-written JSON-LD block
 * had fallen to six of its twelve questions.)
 */
export type QA = { q: string; a: string };

export const FAQ: QA[] = [
  {
    q: 'What is archeus?',
    a: 'The memory and workspace layer for AI coding agents. archeus is free and open source, and it sits in front of the agent: you pick a project, see every session you have ever had in it, and launch the next one with the model, effort, permissions and context you intended. It adds persistent project memory, a session archive you can search and tag, MCP server management, an interactive architecture graph and per-turn cost tracking. It drives three coding CLIs — Anthropic’s Claude Code, OpenAI Codex and pi — with Claude Code much the deepest of them. It is a Python package, MIT licensed, with zero runtime dependencies, and it runs as a terminal UI or a desktop GUI over the same engine.',
  },
  {
    // The old name is still the single biggest query bringing this site
    // impressions — position 7.6 for it and position 3 for the spaced spelling,
    // measured in Search Console — and until this entry existed the site did
    // not contain that name anywhere. Someone arriving on the query that
    // brought them had no confirmation they were in the right place, and a
    // search engine had no sentence tying the two names to one thing. The
    // mentions below are held by `tools/_rename_brand.py` so a future pass
    // cannot rewrite them into a sentence that says nothing.
    q: 'Is archeus the same as claudectl?',
    a: 'Yes. claudectl was renamed to archeus at version 2.0, in September 2026. Same project, same author, same code — the name changed because the tool had stopped being about one CLI. Everything migrates the first time you run it: settings, accounts, per-project launch defaults, the memory graph in each project, snapshots, plans and logs. Nothing is deleted, and the old command keeps working. If you already have the old package, pip install -U claudectl pulls archeus in and carries you across; its final release ships no code of its own, only the dependency. New installs should use pipx install archeus directly.',
  },
  {
    q: 'Where does the name archeus come from, and what is it not?',
    a: 'Archeus is Paracelsus’ name for the vital force that organises living matter — the thing that keeps a body coherent over time, which is what a memory layer does for a codebase. It is not Arceus, the Pokémon, which is spelled with the vowels the other way round and belongs to Nintendo. There is no connection to either. The software called archeus is this one: the Python memory and workspace layer for AI coding agents, installed with pipx install archeus, source at github.com/babarmuhammad/archeus. It is not affiliated with Anthropic.',
  },
  {
    q: 'Is archeus made by Anthropic?',
    a: 'No. archeus is an independent third-party tool built by Babar Muhammad Anas. It is not affiliated with, endorsed by, or supported by Anthropic. Claude and Claude Code are Anthropic’s trademarks. archeus wraps the Claude Code CLI you have already installed and uses the authentication you already have.',
  },
  {
    q: 'Does archeus need an API key?',
    a: 'Not by default. Out of the box it launches the CLI you already have — Claude Code, Codex or pi — using the login that CLI already holds, and it reads the transcripts and settings each one writes to disk — there is nothing to configure and no subscription. A key is only involved if you deliberately point a session somewhere else: archeus can route a session at a local model server, OpenRouter, OmniRoute or anything that serves POST /v1/messages, and that endpoint’s credentials are yours to supply. Everything runs on your machine either way, and the desktop GUI is served on loopback only.',
  },
  {
    q: 'How do I install archeus on Windows, macOS or Linux?',
    a: 'The same command on all three: pipx install archeus (or pip install archeus), or npx archeus to run it without installing it first. It needs Python 3.10 or newer and at least one coding CLI on your PATH — Claude Code, OpenAI Codex or pi. Then run archeus for the terminal UI, or archeus --gui for the desktop app. On Windows the GUI opens in a native window if PyQt6 is installed; everywhere else, and without PyQt6, it opens in your browser.',
  },
  {
    q: 'Where does Claude Code store its sessions?',
    a: 'Under your Claude Code config directory — ~/.claude by default, or wherever CLAUDE_CONFIG_DIR points — in projects/<encoded-path>/<session-id>.jsonl, one JSON object per line. The folder name is your project path with every non-alphanumeric character replaced by a dash, which is lossy and should not be decoded; each transcript line already carries the real cwd. archeus reads these files directly and never modifies them.',
  },
  {
    q: 'How do I see how many tokens Claude Code has used?',
    a: 'archeus reads it out of your own transcripts rather than calling an API, so it works offline and covers every session you have ever run: usage per day, per project, per account and per model, with the cost of a turn broken down. The status line shows the current session’s context pressure and today’s spend on every turn.',
  },
  {
    q: 'How do I uninstall archeus?',
    a: 'pipx uninstall archeus, or pip uninstall archeus. If you installed the status line or hooks, remove them first from the hooks screen so the entries come out of Claude Code’s settings.json cleanly — archeus writes into that file and is the only thing that knows which entries are its own. Your sessions, memory and Claude Code configuration are untouched by the uninstall.',
  },
  {
    q: 'Does archeus work with Claude Code plugins and skills?',
    a: 'Yes, and it ships as one. archeus manages the marketplaces and plugins Claude Code has installed, and has its own plugin with slash commands and skills — /plugin marketplace add babarmuhammad/archeus. It deliberately bundles no hooks in the plugin: its hook manager already installs them per account, and two owners for one settings.json entry means the recall hook runs twice.',
  },
  {
    q: 'How do I manage Claude Code sessions on Windows?',
    a: 'Claude Code stores every session as a JSONL transcript under your config directory, but gives you no way to browse them. archeus lists every session per project with its topic, message count and age, and lets you search, tag, fork, resume, export and archive them — from a terminal UI or a desktop GUI.',
  },
  {
    q: 'How do I reduce Claude Code token usage?',
    a: 'The largest recurring cost is context you pay for on every message. archeus keeps the always-on CLAUDE.md block to a bounded index of about 250 tokens, moves per-module detail into path-scoped rules files that load only when Claude touches those files, and can inject only the memory subgraph a given prompt needs. Its own internal calls route to a cheap economy model, and Plan to Execute runs an expensive model once for the plan and a cheap one for execution.',
  },
  {
    q: 'What is a Claude Code MCP server manager?',
    a: 'MCP servers are configured in JSON and are otherwise invisible — you cannot easily tell which are connected to a project or what tools they expose. archeus detects the servers configured for each project, shows them at a glance, and can run an analysis that lists a server’s actual tools into your global CLAUDE.md inside a re-updatable block.',
  },
  {
    q: 'How do I run multiple Claude accounts at the same time?',
    a: 'Claude Code selects its account through the CLAUDE_CONFIG_DIR environment variable. archeus detects every configured account, merges their projects into one list, shows per-account usage side by side, and sets that variable for you when it launches a session, so you pick the account at launch rather than juggling environment variables.',
  },
  {
    q: 'Does archeus require any Python dependencies?',
    a: 'No. It runs on the Python standard library alone and needs Python 3.10 or newer. PyQt6 is optional and only needed for the native desktop shell — without it the GUI opens in your browser instead.',
  },
  {
    q: 'Does archeus work on macOS and Linux, or only Windows?',
    a: 'It runs on all three, and CI tests all three. It is Windows-first in that Windows gets the widest Python version matrix and the most real-world use, so rough edges are likelier on macOS and Linux. Bug reports from those platforms are welcome.',
  },
  {
    q: 'How is archeus different from Claude Code’s built-in /resume?',
    a: '/resume reattaches you to a recent session in the current directory. archeus treats your sessions as a searchable archive across every project and every account, adds tags, export, fork and archive, and controls what model, effort, permissions and project context a session launches with. /resume answers "put me back"; archeus answers "what have I done here, and how should the next session start".',
  },
  {
    q: 'Can I use a cheaper model to execute a plan made by a stronger model?',
    a: 'Yes — that is what Plan to Execute does. It runs a headless planning pass with the strong model, shows you the plan for approval or editing, then hands the approved plan to a cheaper model to carry out. Free execution routes that half through OmniRoute’s free tier.',
  },
  {
    q: 'What happens to my project memory after /compact?',
    a: '/compact discards detail from the conversation, which is where context loss usually bites. archeus’s memory lives outside the transcript — in the project’s memory graph and its rules files — so it is re-injected at the next launch regardless of what the conversation dropped.',
  },
  {
    q: 'Does archeus have a GUI, or is it terminal-only?',
    a: 'Both, over the same engine. The terminal UI is the default. Running archeus --gui opens a desktop GUI: a native window if PyQt6 is installed, otherwise your browser, served over loopback only.',
  },
  {
    q: 'Is archeus free and open source?',
    a: 'Yes, MIT licensed and free. It uses your existing Claude Code authentication and adds no subscription and no API key of its own.',
  },
  {
    q: 'Can I install it from PyPI?',
    a: 'Yes: pipx install archeus, or pip install archeus. It also ships as a Claude Code plugin if you would rather stay inside the session.',
  },
  {
    q: 'Does archeus work with coding agents other than Claude Code?',
    a: 'Yes — OpenAI Codex and pi, with nothing to configure: archeus looks for each CLI’s binary and its home directory, and one it cannot find is simply not offered. Their projects, sessions, previews, models and token spend merge into the same lists, one memory graph is delivered to all three (CLAUDE.md for Claude Code, AGENTS.md for Codex, both for pi), skills install into every one of them, and any of them can be launched from the same picker — each with its own model list and its own effort scale. Claude Code is much the deepest of the three: hooks, MCP servers, subagents, plugins, output styles and checkpoints are its alone, and every one of those screens says which CLI cannot do it and why rather than hiding the gap. The other half of the goal shipped earlier: a session can run against a local server, OpenRouter, OmniRoute or any endpoint that serves POST /v1/messages. Claude Code is the first surface, not the boundary, and it is no longer the only one — a harness of archeus’ own remains a long-term goal.',
  },
  {
    q: 'Can I run archeus against a local model, or something other than Anthropic?',
    a: 'Yes. Settings → Model provider takes any endpoint that serves POST /v1/messages — Ollama, llama.cpp, vLLM or another self-hosted server on your own machine, OpenRouter, or OmniRoute’s free tier — and a translating gateway handles backends that speak the OpenAI chat format instead. The session is still a real Claude Code session, so agents, skills, hooks, MCP servers, slash commands and checkpoints all keep working; what a backend swap genuinely costs is subagents, prompt caching, extended thinking and web_search, and that is written down rather than glossed. archeus’ own internal Claude calls — memory extraction, lesson distillation, review, the generators — can be routed there too, but that is opt-in and off by default, because they run unattended and moving them changes which account is billed.',
  },
];

export const faqJsonLd = () => ({
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: FAQ.map(({ q, a }) => ({
    '@type': 'Question',
    name: q,
    acceptedAnswer: { '@type': 'Answer', text: a },
  })),
});
