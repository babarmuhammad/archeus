# archeus

**The memory and workspace layer for AI coding agents.** Persistent per-project
memory, every session you have ever had, and control over what the next one costs.

```bash
npx archeus
```

archeus is written in Python; this package is the launcher. It runs `archeus` if
you already have it, and otherwise installs it first — with `pipx` where that is
available, `pip --user` otherwise — printing the exact command before it runs.
Python 3.10 or newer is required.

To install it directly instead:

```bash
pipx install archeus        # or: pip install archeus
```

## What it does

- **Per-project memory that survives the session.** A semantic graph of your
  codebase, injected as a short digest rather than a wall of text, with the
  detail available on demand.
- **Every session you have ever had**, searchable, resumable, with what each one
  cost.
- **Launch control per project** — model, effort, permission mode, and the
  provider the session talks to.
- **A terminal UI and a desktop GUI** over the same data.

Works with Claude Code, OpenAI Codex and pi. Zero runtime dependencies beyond the Python
standard library.

Site: <https://claudectl.space>  
Manual: <https://docs.claudectl.space>  
Source and issues: <https://github.com/babarmuhammad/archeus>  
Python package: <https://pypi.org/project/archeus/>

MIT licensed.
