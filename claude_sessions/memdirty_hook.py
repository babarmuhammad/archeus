"""Claude Code hook — record which files Claude just changed.

Fires on `PostToolUse` for Edit/Write/NotebookEdit and appends the edited path
to `<cwd>/.archeus/memory/dirty.log`. The auto-memory scheduler drains that
list and knows what to re-extract without walking the project at all.

Why this exists: staleness was decided by SHA-256-ing every source file in the
project, on every scheduler tick and every project open. The hash sweep is now
stat-prefiltered and cheap, but it is still O(files); an edit signal is O(1) and
arrives the moment the change happens.

Why not `FileChanged`: that event's matcher is a list of literal FILENAMES to
watch, not a glob over a codebase — it is built for `.env`-style sentinels. The
`memory-stale-on-change` preset was wired to it (and, separately, to a script
that never touched memory at all), so it had never once marked anything stale.

Honest limit: this sees only what Claude Code edits. Changes from your own
editor, a `git pull` or another tool are caught by the hash sweep, which remains
the reconciler rather than being replaced.

Append-only and never blocks: exit 0 on every failure. One line per edit, so
concurrent sessions cannot lose each other's entries — the same discipline the
recall hook's `hits.log` uses.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Claude Code captures stdout as a PIPE, so CPython picks the locale codepage
# (cp1252 on Windows) and any non-ASCII path either mojibakes or raises.
#
# Guarded because `sys.stdout` is None in a windowed process (pythonw with no
# console), and a hook must degrade to "no pretty output" rather than die at
# import. Every hook in this package now does this for the same reason.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError, OSError):
    pass

#: a session that rewrites a thousand files should not grow an unbounded log —
#: past this the sweep is cheaper than the list, and it is only a hint anyway
MAX_LINES = 2000


def dirty_log_path(cwd):
    """Where this hook appends. `memory` OWNS the path — a hook is an entry
    point, so nothing in the package may import one as a library."""
    from claude_sessions.memory import dirty_log_path as _p
    return _p(cwd)


def record(cwd, path):
    """Append one edited path. Best-effort, append-only."""
    if not path:
        return 0
    p = dirty_log_path(cwd)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if os.path.isfile(p) and os.path.getsize(p) > MAX_LINES * 260:
            return 0                       # the sweep will catch up instead
        with open(p, 'a', encoding='utf-8') as f:
            f.write(os.path.abspath(path) + '\n')
    except Exception:
        pass
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    if data.get('hook_event_name') != 'PostToolUse':
        return 0
    cwd = data.get('cwd') or os.getcwd()
    ti = data.get('tool_input') or {}
    if not isinstance(ti, dict):
        return 0
    # Edit/Write use `file_path`; NotebookEdit uses `notebook_path`
    return record(cwd, ti.get('file_path') or ti.get('notebook_path') or '')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
