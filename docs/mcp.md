---
description: >-
  Add, remove and inspect MCP servers from archeus — connection state at a glance, a live
  status footer, and tool documentation written into the global CLAUDE.md.
---

# MCP servers

- **Full management** — add, remove, and inspect MCP servers via `claude mcp` (scopes local/user/project, transports stdio/http/sse, env vars and headers)
- **Three states, all visible** — ✔ connected, `!` needs authentication, ✘ failed to connect or timed out. A server that cannot connect is the one you most need to see, so it is listed with its error rather than omitted
- **Status footer** — connected servers shown live on the main screen
- **Tool documentation** — analyze any server's tools and write the docs into the global `~/.claude/CLAUDE.md`

Each analyzed server gets its own sentinel-delimited section in the global file, so
re-running the analysis updates only that server — see
[Global CLAUDE.md](configuration.md#global-claudemd).

MCP servers also appear in the [context weight audit](usage.md), because their
tool definitions ride in the model's context on every turn.
