---
title: More than one CLI — Claude Code, Codex and pi
description: >-
  archeus reads the sessions, projects and token spend of Claude Code, OpenAI Codex and pi, gives all three one memory graph, and launches any of them.
---

# More than one CLI

⚙ Settings → **Which tools archeus shows**, and the tab strip on **New session**.

archeus began with one coding CLI behind it. It now reads three, and the distinction that
makes that work is worth stating once:

- a **provider** is an endpoint. [Model providers](providers.md) repoint `ANTHROPIC_BASE_URL`
  and the same `claude` binary talks to a different model.
- a **harness** is the binary itself, plus the conventions it keeps on disk — where its
  transcripts live, what its instructions file is called, what a session id even is.

The two are orthogonal. OmniRoute is a provider; Codex is a harness. The launch picker
shows both in one strip because they are both answers to "what runs this session", but
they are not the same kind of answer.

## What archeus finds on its own

Nothing to configure. archeus looks for each CLI's binary and its home directory, and a
CLI it cannot find is simply not offered — a home with no binary is a leftover, not an
installation.

| CLI | Home | Instructions file | Found via |
|---|---|---|---|
| **Claude Code** | `~/.claude` (and every other account) | `CLAUDE.md` | `CLAUDE_CONFIG_DIR`, `~/.local/bin`, `PATH` |
| **OpenAI Codex** | `~/.codex` | `AGENTS.md` | `CODEX_HOME`, its hashed install directory, `PATH` |
| **pi** | `~/.pi/agent` | `AGENTS.md` | `PI_CODING_AGENT_DIR`, npm's global bin, `PATH` |

Everything that follows works off that: the project list, the sessions list, previews,
turn counts, models, token spend, search, usage and the dashboard all merge across every
CLI you have.

## One memory graph, three CLIs

This is the part that is not a convenience.

A project's [memory graph](memory.md) is the project's — what it is, how it is laid out,
what has been learned about it. It is not Claude Code's memory of the project, and it
would be absurd for it to be rebuilt once per tool. So archeus keeps one graph and
delivers the same digest into every instructions file an installed CLI reads: `CLAUDE.md`
for Claude Code, `AGENTS.md` for Codex, and both for pi, which reads either.

A machine with no Codex never grows an `AGENTS.md`, and a CLI you switch off stops getting
one.

The [agent routing table](agents.md) deliberately does **not** follow. Delegating to a
subagent is a Claude Code capability; writing "delegate with the Agent tool" into
`AGENTS.md` would instruct Codex to use a tool it does not have.

[Skills](agents.md#skills) do follow, because `SKILL.md` is the
[Agent Skills standard](https://agentskills.io/specification) and all three read the same
file. Installing one personally puts it in every account *and* every CLI; installing one
into a project writes `.claude/skills` and `.agents/skills` — two directories, not three,
because `.agents/skills` is the cross-harness convention that Codex and pi share.

## Choosing one at launch

**New session** opens on a tab strip: your installed CLIs, then each configured backend by
name. The default is Claude Code and you can change it in ⚙ Settings → Defaults →
**Starts on**.

The tab is above the rest of the form because it decides what the rest of the form even
means. A Codex session has no worktree and no name-at-launch; a pi session has no
permission mode. Those fields are not greyed out — they are gone, and the strip says why:

> Codex names a session afterwards, with `thread name set`, not at launch.

A resume has no strip at all. A session already on disk belongs to the CLI that wrote it,
and a Codex thread cannot be resumed by pi.

## What each CLI cannot do here

archeus never pretends. A screen a CLI has no equivalent for is shown greyed with the
reason, and a button on a session row works the same way.

| | Claude Code | Codex | pi |
|---|---|---|---|
| Sessions, resume, fork | ✅ | ✅ | ✅ |
| Token spend & usage | ✅ | ✅ | ✅ |
| Project memory | ✅ | ✅ | ✅ |
| Skills | ✅ | ✅ | ✅ |
| Archive a session | ✅ | ✅ | — *no archive; a session is kept or deleted* |
| Checkpoints (`/rewind`) | ✅ | — *SQLite, not a file-history store* | — *branches inside one session file* |
| Hooks | ✅ | — *`hooks.json`, behind a trust hash* | — *TypeScript extensions instead* |
| MCP servers | ✅ | — *`config.toml`* | — *no MCP client* |
| Subagents | ✅ | — *`.agents`* | — *none* |
| Plugins & marketplaces | ✅ | — *its own* | — *`pi install`* |
| Output styles | ✅ | — | — |
| Accounts | ✅ | — *one login per home* | — *one `auth.json` per home* |
| Status line | ✅ | — | — *draws its own* |

The gaps that are archeus reading Claude Code's file for something the other CLI keeps
elsewhere are marked as such on the page itself, so you can tell "this tool does not have
it" from "archeus has not got to it yet".

## Turning one off

⚙ Settings → **Which tools archeus shows**.

Off means everywhere — the launch tabs, the project list, the sessions list, the usage
table, and the instructions files that get a memory block. Hiding it from one surface and
leaving it in the others is what makes a setting feel broken.

Nothing is uninstalled and nothing on disk is touched. Switch it back on and its projects
come straight back.

Claude Code is listed and locked. It is not only a CLI archeus reads: it is the binary
archeus itself runs for memory extraction, lessons, CLAUDE.md generation and every other
AI feature, so switching it off would hide the app's own engine while it kept running.

## What archeus will not guess

Two deliberate refusals, both the same discipline [checkpoints](statusline.md#checkpoints)
already follows:

- **A Codex thread's transcript is named by its index, not derived from its id.** archeus
  reads the path out of `state_*.sqlite` rather than reconstructing it.
- **A pi session directory's name is never decoded.** pi maps every path separator and the
  drive colon to `-`, which is lossy; the first line of every session file carries the real
  working directory, and that is what archeus reads.

Both stores are opened **read-only**. archeus never writes to another CLI's session state.
