"""The text the SessionStart rule hooks inject, owned in one importable place.

These strings live here rather than inside the hook scripts because two things
need them: the hook itself, and the context-weight audit, which counts what
every always-on surface costs per session.

A hook script is an ENTRY POINT. It reconfigures stdout at import, because
Claude Code hands it a pipe — so importing one as a library runs that line in
whatever process did the importing, and `sys.stdout` is None in a windowed one
(pythonw with no console, i.e. the GUI). `ctxaudit` imported both of these for
their rule text inside a bare `except Exception: pass`, so in the GUI the
import failed and the audit silently under-reported these hooks' cost; the same
pattern in `memory` took the entire auto-memory cycle down. One owner, and the
dependency points hook -> library only.
"""

MINIMAL_CODE = (
    "Code minimization (archeus): read/understand fully, then write the LEAST "
    "code that works. Before writing, stop at the first hit — 1) needed at all? "
    "(YAGNI) 2) already in this repo? reuse 3) stdlib? 4) native platform feature? "
    "5) an installed dependency? 6) one line? 7) only then the minimum that works. "
    "No speculative abstraction or dead scaffolding; keep readability and full safety."
)

CONCISE = (
    "Concise output (archeus): answer directly — no preamble, no narration of "
    "what you are about to do, no recap of what you just did. Never re-print "
    "unchanged code; reference file:line instead. Explain only what was asked, "
    "at the depth asked. Skip closing summaries when the result is visible from "
    "the change itself. Prefer editing files over printing their content."
)
